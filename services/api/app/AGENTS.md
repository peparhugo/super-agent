# Application Agents (services/api/app)

## Scope
Instructions for runtime, memory, registry, and worker modules under `services/api/app`.

## When to use
- Implementing runtime orchestration, agent memory, registry entries, or worker tasks.
- Adjusting domain-specific evaluation logic.

## Coding standards
- Favor small, testable functions and explicit data models.
- Use Pydantic v2 models for request/response schemas.
- Keep FastAPI routers thin; push logic into service modules.
- Do not wrap imports in try/except blocks.

## Verification
- Ensure any new orchestration logic has a CLI entry point or unit-testable functions.
- Add or update runbook steps in `PLANS.md` when module responsibilities change.
