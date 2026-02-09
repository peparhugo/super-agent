# Super Agent API Stack

This service hosts the FastAPI application, Celery workers, and supporting infrastructure.

## Repository layout

```
services/api/
├── app/
│   ├── runtime/
│   ├── memory/
│   ├── registry/
│   └── worker/
│       └── tasks/
├── policies/
├── Dockerfile
├── pyproject.toml
└── worker/
    └── Dockerfile
```

## Environment configuration

Copy the example environment file and update secrets as needed:

```bash
cp .env.example .env
```

The `docker-compose.yml` file loads `.env` and wires the values into the API, worker, and supporting services.

## Boot the full stack

From the repository root:

```bash
docker compose up --build
```

Optional Adminer UI (database browser):

```bash
docker compose --profile admin up --build
```

## Run services locally without Docker

Install dependencies and run the API:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e services/api
uvicorn app.main:app --reload
```

Run a Celery worker (from the repo root):

```bash
source .venv/bin/activate
celery -A app.worker.celery_app worker --loglevel=info
```

Run Celery beat:

```bash
source .venv/bin/activate
celery -A app.worker.celery_app beat --loglevel=info
```
