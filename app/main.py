import os
import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, status
from pydantic import BaseModel, Field
from sqlalchemy import Float, String, create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ItemResponse(ItemCreate):
    id: int


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rows_received: Mapped[int] = mapped_column(nullable=False)
    rows_accepted: Mapped[int] = mapped_column(nullable=False)
    rows_rejected: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class IngestedRecord(Base):
    __tablename__ = "ingested_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)


class PipelineRunResponse(BaseModel):
    id: int
    filename: str
    status: str
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    created_at: datetime


class IngestedRecordResponse(BaseModel):
    id: int
    run_id: int
    name: str
    amount: float


database_url = os.getenv("DATABASE_URL", "sqlite:////tmp/pipeline.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    return {"message": "Pipeline is running"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return {"status": "ok", "database": "ok"}


@app.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    item = Item(name=payload.name)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/items", response_model=list[ItemResponse])
def list_items(db: Session = Depends(get_db)):
    return db.scalars(select(Item).order_by(Item.id)).all()


@app.get("/items/{item_id}", response_model=ItemResponse)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
    return item


@app.post("/pipeline/ingest", response_model=PipelineRunResponse)
async def ingest_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only CSV uploads are supported",
        )

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded",
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not {"name", "amount"}.issubset(
        set(reader.fieldnames)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must contain name and amount columns",
        )

    run = PipelineRun(
        filename=file.filename,
        status="running",
        rows_received=0,
        rows_accepted=0,
        rows_rejected=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()

    for row in reader:
        run.rows_received += 1
        name = (row.get("name") or "").strip()
        try:
            amount = Decimal((row.get("amount") or "").strip())
            if not name or not amount.is_finite():
                raise InvalidOperation
            normalized_amount = float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError):
            run.rows_rejected += 1
            continue

        db.add(
            IngestedRecord(
                run_id=run.id,
                name=name.title(),
                amount=normalized_amount,
            )
        )
        run.rows_accepted += 1

    run.status = "completed"
    db.commit()
    db.refresh(run)
    return run


@app.get("/pipeline/runs", response_model=list[PipelineRunResponse])
def list_pipeline_runs(db: Session = Depends(get_db)):
    return db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc())).all()


@app.get("/pipeline/runs/{run_id}/records", response_model=list[IngestedRecordResponse])
def list_ingested_records(run_id: int, db: Session = Depends(get_db)):
    if db.get(PipelineRun, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pipeline run not found")
    return db.scalars(
        select(IngestedRecord).where(IngestedRecord.run_id == run_id).order_by(IngestedRecord.id)
    ).all()
