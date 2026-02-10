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

## Authorization policies and sandbox profiles

OPA policies live in `services/api/policies/` and are queried by the runtime/worker before
tool execution, memory reads, and candidate promotion. The default policy inputs include
agent role, risk level, and an execution profile to ensure least-privilege tool access.

### Sandbox execution profiles

Tools must run with restricted execution profiles (no Docker socket access and constrained
filesystem visibility). The default profile used by the runtime is `sandbox_standard`.

| Profile | Docker socket | Filesystem access | Intended use |
| --- | --- | --- | --- |
| `sandbox_low` | Disabled | Read-only + temp | Low-risk read-only tools |
| `sandbox_standard` | Disabled | Workspace-scoped + temp | Standard tool execution |
| `sandbox_sensitive` | Disabled | Workspace-scoped + temp | Higher-risk tools with stricter review |
| `sandbox_privileged` | Disabled | Workspace-scoped + temp | Admin-only tools (still no Docker socket) |

The `filesystem` value sent to OPA is one of `readonly`, `workspace`, or `temp`, and the
policies deny any execution profile that requests Docker socket access.

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
