from __future__ import annotations

import asyncio
from typing import Any

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.authz import AuthorizationError, authorize_promotion, normalize_risk, normalize_role
from app.db import get_sessionmaker
from app.eval.harness import CheckResult, run_all_checks, summarize_results
from app.models import Agent, EvalResult, EvalRun, RegistryStatus, Skill
from app.registry.agents import transition_agent_status
from app.registry.skills import transition_skill_status
from app.settings import get_settings
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)


def _candidate_payload(candidate: Agent | Skill) -> dict[str, Any]:
    if isinstance(candidate, Skill):
        return {
            "candidate_type": "skill",
            "name": candidate.name,
            "version": candidate.version,
            "description": candidate.description,
            "spec": candidate.spec,
        }
    return {
        "candidate_type": "agent",
        "name": candidate.name,
        "version": candidate.version,
        "description": candidate.description,
        "config": candidate.config,
    }


def _candidate_risk_level(candidate: Agent | Skill) -> str:
    if isinstance(candidate, Skill):
        spec = candidate.spec or {}
        return normalize_risk(spec.get("risk_level") or spec.get("risk"))
    config = candidate.config or {}
    return normalize_risk(config.get("risk_level") or config.get("risk"))


def _check_to_result(eval_run_id, check: CheckResult) -> EvalResult:
    return EvalResult(
        eval_run_id=eval_run_id,
        score=check.score,
        metrics={
            "passed": check.passed,
            "details": check.details,
            "check": check.name,
        },
    )


async def _evaluate_candidate(session, candidate: Agent | Skill) -> dict[str, Any]:
    payload = _candidate_payload(candidate)
    candidate_type = payload["candidate_type"]
    eval_run = EvalRun(
        agent_id=candidate.agent_id if isinstance(candidate, Agent) else None,
        status="running",
        parameters={
            "candidate_type": candidate_type,
            "candidate_id": str(candidate.agent_id if isinstance(candidate, Agent) else candidate.skill_id),
            "candidate_version": candidate.version,
        },
    )
    session.add(eval_run)
    await session.flush()

    results = run_all_checks(candidate_type, payload)
    eval_results = [_check_to_result(eval_run.eval_run_id, result) for result in results]
    session.add_all(eval_results)
    summary = summarize_results(results)
    eval_run.status = "completed" if summary["passed"] else "failed"
    await session.commit()

    if summary["passed"]:
        settings = get_settings()
        try:
            decision = await authorize_promotion(
                settings,
                agent_role=normalize_role("worker"),
                agent_risk_level="medium",
                candidate_type=candidate_type,
                candidate_risk_level=_candidate_risk_level(candidate),
            )
        except AuthorizationError as exc:
            logger.warning("Promotion authorization failed: %s", exc)
            summary["passed"] = False
            summary["promotion_allowed"] = False
            return summary
        if not decision.allowed:
            logger.info("Promotion denied for %s: %s", candidate_type, decision.reasons)
            summary["passed"] = False
            summary["promotion_allowed"] = False
            return summary
        if isinstance(candidate, Skill):
            await transition_skill_status(
                session, skill_id=str(candidate.skill_id), new_status=RegistryStatus.ACTIVE
            )
        else:
            await transition_agent_status(
                session, agent_id=str(candidate.agent_id), new_status=RegistryStatus.ACTIVE
            )
        summary["promotion_allowed"] = True
    return summary


async def _evaluate_candidates() -> dict[str, int]:
    session_factory = get_sessionmaker(role="worker")
    async with session_factory() as session:
        skills = (
            await session.execute(select(Skill).where(Skill.status == RegistryStatus.CANDIDATE))
        ).scalars().all()
        agents = (
            await session.execute(select(Agent).where(Agent.status == RegistryStatus.CANDIDATE))
        ).scalars().all()

        passed = 0
        failed = 0
        for candidate in [*skills, *agents]:
            summary = await _evaluate_candidate(session, candidate)
            if summary["passed"]:
                passed += 1
            else:
                failed += 1
        return {"passed": passed, "failed": failed}


@celery_app.task
def evaluate_candidates() -> dict[str, int]:
    result = asyncio.run(_evaluate_candidates())
    logger.info("Evaluation summary: %s", result)
    return result
