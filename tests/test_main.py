import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import Base, app, get_db


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Pipeline is running"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_create_and_read_item():
    create_response = client.post("/items", json={"name": "example"})
    assert create_response.status_code == 201
    item = create_response.json()

    list_response = client.get("/items")
    assert list_response.status_code == 200
    assert list_response.json() == [item]

    get_response = client.get(f"/items/{item['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == item


def test_item_not_found():
    response = client.get("/items/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "item not found"}


def test_csv_ingestion_transforms_valid_rows():
    response = client.post(
        "/pipeline/ingest",
        files={"file": ("sales.csv", b"name,amount\nalice,12.345\nbob,\n", "text/csv")},
    )

    assert response.status_code == 200
    run = response.json()
    assert run["filename"] == "sales.csv"
    assert run["status"] == "completed"
    assert run["rows_received"] == 2
    assert run["rows_accepted"] == 1
    assert run["rows_rejected"] == 1


def test_csv_ingestion_requires_columns():
    response = client.post(
        "/pipeline/ingest",
        files={"file": ("invalid.csv", b"product,price\none,10\n", "text/csv")},
    )

    assert response.status_code == 400
    assert "name and amount" in response.json()["detail"]


def test_ingestion_records_can_be_read_by_run():
    response = client.post(
        "/pipeline/ingest",
        files={"file": ("sales.csv", b"name,amount\nalice,12.345\n", "text/csv")},
    )
    run_id = response.json()["id"]

    records_response = client.get(f"/pipeline/runs/{run_id}/records")
    assert records_response.status_code == 200
    assert records_response.json() == [
        {"id": 1, "run_id": run_id, "name": "Alice", "amount": 12.35}
    ]
