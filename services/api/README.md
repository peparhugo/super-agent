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

## Knowledge ingestion and summarization operations

The API now supports filesystem-backed knowledge ingestion rooted at `knowledge/`.
Use the default domain-aware structure:

```text
knowledge/
├── corporate/incoming/
├── academic/incoming/
└── shared/incoming/
```

### How to add documents

1. Add UTF-8 text-like files (`.md`, `.txt`, `.rst`, `.json`, `.yaml`, `.yml`, `.csv`) into one of the domain folders under `knowledge/<domain>/incoming/`.
2. The ingestion watcher discovers new/changed files and records each source in Postgres (`knowledge_documents`) with checksum + lifecycle metadata.
3. For each discovery and summary action, append-only memory events are written (`knowledge.document.discovered`, `knowledge.document.summarized`).

### How summaries and indexing work

- `app.memory.ingest.run_ingestion_cycle` scans the filesystem, updates Postgres metadata, summarizes pending documents through the LLM endpoint, and upserts vectors to Qdrant.
- Each vector payload uses compact summary text and includes metadata fields like `source`, `date`, and `domain` for retrieval filters.
- Celery beat schedules the workflow via `app.worker.tasks.ingest.ingest_knowledge_documents`.

### Triggering or re-running indexing

Run one ingestion cycle manually:

```bash
source .venv/bin/activate
KNOWLEDGE_WATCH_ONCE=true python -m app.memory.ingest
```

Run continuously as a local watcher:

```bash
source .venv/bin/activate
python -m app.memory.ingest
```

Trigger through Celery directly:

```bash
source .venv/bin/activate
celery -A app.worker.celery_app call app.worker.tasks.ingest.ingest_knowledge_documents
```

Force re-index for an updated file by editing its contents. The checksum changes, so the document is marked discovered again and re-summarized/re-embedded on the next cycle.

### Updating AGENTS/skills when adding new knowledge domains

When introducing new domain folders or ingestion conventions:

1. Update repository-level `AGENTS.md` domain guidance to describe the new domain and intended use.
2. Update any domain skill definitions under `.agents/skills/` so prompts, constraints, and evaluation criteria include the new knowledge source.
3. Verify Celery beat and retrieval filters still map cleanly to the revised domain taxonomy (`domain` metadata in Qdrant + Postgres).
