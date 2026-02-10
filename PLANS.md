# ExecPlans

Each plan is self-contained with verification steps and references Milestone 1 (scaffolding) and Milestone 4 (runtime structure alignment).

## Skill Library ExecPlan
**Objective**: Maintain domain-specific skills under `.agents/skills/` with progressive disclosure assets.

**Dependencies**: Milestone 1 repo scaffolding, Milestone 4 runtime structure alignment.

**Execution steps**
1. Define or update skill directories for each domain agent.
2. Add `SKILL.md` with YAML front matter and minimal actionable guidance.
3. Place optional scripts or references in `scripts/` or `references/` folders.
4. Link skills in the top-level `AGENTS.md`.

**Verification**
- Confirm skill directories exist under `.agents/skills/`.
- Review `AGENTS.md` for links to each skill module.

## RAG Pipeline ExecPlan
**Objective**: Plan retrieval-augmented generation ingestion, indexing, and query flow.

**Dependencies**: Milestone 1 repo scaffolding, Milestone 4 runtime structure alignment.

**Execution steps**
1. Define data ingestion sources and metadata schemas.
2. Specify embedding/indexing strategy (vector store, filters, refresh cadence).
3. Identify runtime modules that will own retrieval logic.
4. Add evaluation hooks for precision/recall and grounding.

**Verification**
- Document ingestion inputs and retrieval owners in the plan.
- Ensure runtime modules referenced are present in `services/api/app`.

## MCP Integration ExecPlan
**Objective**: Integrate MCP servers and tool execution via the Agents SDK.

**Dependencies**: Milestone 1 repo scaffolding, Milestone 4 runtime structure alignment.

**Execution steps**
1. Define MCP server lifecycle (start/stop) and configuration inputs.
2. Wire MCP toolsets into planner/developer/tester agents.
3. Capture trace logs and thread IDs for each orchestration run.
4. Document CLI usage and environment variables.

**Verification**
- Run `python scripts/orchestrate_agents.py --help`.
- Ensure trace log output directory is created on execution.

## Knowledge Ingestion ExecPlan
**Objective**: Bring new corporate and academic knowledge into the system with provenance.

**Dependencies**: Milestone 1 repo scaffolding, Milestone 4 runtime structure alignment.

**Execution steps**
1. Define ingestion manifest formats for documents and datasets.
2. Capture provenance, licensing, and update cadence.
3. Schedule ingestion jobs and assign owners.
4. Document expected outputs and retention policy.
5. Implement `app.memory.ingest` watcher + Celery beat schedule for continuous discovery/summarization.

**Verification**
- Review manifest schema documentation for completeness.
- Confirm provenance steps are documented in skill references.
- Run `KNOWLEDGE_WATCH_ONCE=true python -m app.memory.ingest` and verify Postgres (`knowledge_documents`) plus Qdrant summary payloads are updated.

## Multi-Agent Orchestration ExecPlan
**Objective**: Execute planner/developer/tester roles with traceability and MCP tooling.

**Dependencies**: Milestone 1 repo scaffolding, Milestone 4 runtime structure alignment.

**Execution steps**
1. Provide prompts and role instructions for planner, developer, and tester agents.
2. Execute agents in sequence, passing summaries between roles.
3. Store thread IDs, timestamps, and trace metadata in logs.
4. Publish run artifacts (plans, decisions, and results).

**Verification**
- Run `python scripts/orchestrate_agents.py --role planner --input "test"`.
- Inspect trace log output for thread ID and role execution entries.
