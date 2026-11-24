
# FastAPI CI/CD Pipeline

## Overview

This project demonstrates a containerized FastAPI service integrated with a CI/CD pipeline. It simulates a lightweight data platform workflow, focusing on automated testing, containerization, and reproducible development environments.

## Features

* FastAPI-based service with REST endpoints
* Dockerized application for consistent runtime environments
* Automated testing using pytest
* CI pipeline for continuous integration and validation
* Modular project structure for scalability

## Tech Stack

* Python (FastAPI)
* Docker
* Pytest
* GitHub Actions

## Project Structure

```
ci-cd-data-pipeline/
│── app/                # Application code
│── tests/              # Unit tests
│── Dockerfile          # Container definition
│── requirements.txt    # Dependencies
│── .github/workflows/  # CI pipeline
```

## Getting Started

### Prerequisites

* Docker installed
* Python 3.11+ (for local development)
* Git

### Run Locally (Docker)

```
docker build -t data-pipeline .
docker run --rm -p 8000:8000 data-pipeline
```

Access the service:

```
http://localhost:8000
```

Health check:

```
http://localhost:8000/health
```

### Run a Published Image

Images are published to GitHub Container Registry for pushes to `main`:

```
docker pull ghcr.io/kennethsfulton/fastapi-ci-cd-pipeline:latest
docker run --rm -p 8000:8000 ghcr.io/kennethsfulton/fastapi-ci-cd-pipeline:latest
```

### Run Tests Locally

```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m pytest
```

## CI/CD Pipeline

The CI pipeline is triggered on every push and pull request. It:

1. Checks out the code
2. Installs dependencies
3. Runs automated tests

This ensures code quality and prevents regressions.

## Future Enhancements

* Integrate PostgreSQL for persistent storage
* Add data ingestion and transformation workflows
* Build and push Docker images in CI
* Deploy to a cloud or Kubernetes environment
* Add infrastructure as code (Terraform)

## Purpose

This project is designed to demonstrate practical CI/CD, containerization, and backend development skills aligned with data engineering and platform engineering roles.

