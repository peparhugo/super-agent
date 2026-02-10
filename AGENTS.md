# AGENTS

## Purpose
This repository coordinates multi-agent automation for corporate and academic domains, with a shared API runtime in `services/api`. Use these instructions when planning or implementing workflows across the stack.

## Domain agents
### Corporate domain agent
**When to use**
- Enterprise program management, compliance audits, business analytics, stakeholder-ready reporting.
- Security, risk, and governance requirements for production releases.

**Primary focus**
- Regulatory alignment, audit trails, SLA/SLO definitions, executive summaries.
- Clear success criteria, acceptance tests, and rollout/rollback plans.

### Academic domain agent
**When to use**
- Literature review synthesis, research experiment planning, benchmarking, and reproducibility.
- Drafting citations, evaluating methods, or structuring lab protocols.

**Primary focus**
- Research methodology, data provenance, reproducible experiments, citation integrity.
- Explicit assumptions, limitations, and dataset availability.

## Build/test commands
Run from the repository root:
- `docker compose up --build`
- `docker compose --profile admin up --build`
- `python -m venv .venv`
- `source .venv/bin/activate`
- `pip install -e services/api`
- `uvicorn app.main:app --reload`
- `celery -A app.worker.celery_app worker --loglevel=info`
- `celery -A app.worker.celery_app beat --loglevel=info`

## Coding standards
- Python 3.11+, type hints for public functions, and structured logging.
- Prefer async-friendly patterns in FastAPI handlers.
- Keep domain logic in `services/api/app` modules; avoid cross-module imports without clear ownership.
- Do not wrap imports in try/except blocks.
- Include explicit verification steps in plans and runbooks.

## Dependencies
- `fastapi`, `celery`, `sqlalchemy`, `qdrant-client`, `redis`, `mcp`, `openai-agents`.
- Local runtime uses Docker Compose and `.env` configuration.

## Skills and knowledge modules
- Corporate domain skill: `.agents/skills/corporate-domain/`.
- Academic domain skill: `.agents/skills/academic-domain/`.
- Refer to `PLANS.md` for execution plans tied to runtime structure (Milestones 1 and 4).
