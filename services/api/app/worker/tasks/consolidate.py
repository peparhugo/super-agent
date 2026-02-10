from __future__ import annotations

import asyncio
import datetime
import os
from collections import defaultdict
from typing import Any

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import Event, RegistryStatus, Skill, Agent
from app.registry.agents import create_agent
from app.registry.skills import create_skill
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)


def _categorize_event(event: Event) -> str:
    event_type = event.event_type.lower()
    if "skill" in event_type or "tool" in event_type:
        return "skill"
    return "agent"


def _candidate_name(event_type: str) -> str:
    return f"auto-{event_type.replace('.', '-').replace(' ', '-')}"


async def _existing_candidate_names(session) -> set[str]:
    skills = (await session.execute(select(Skill.name))).scalars().all()
    agents = (await session.execute(select(Agent.name))).scalars().all()
    return {*(skills or []), *(agents or [])}


async def _consolidate_candidates() -> dict[str, int]:
    lookback_hours = float(os.getenv("CONSOLIDATE_LOOKBACK_HOURS", "24"))
    min_events = int(os.getenv("CONSOLIDATE_MIN_EVENTS", "3"))
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=lookback_hours)
    session_factory = get_sessionmaker(role="worker")
    async with session_factory() as session:
        events = (
            await session.execute(select(Event).where(Event.created_at >= since))
        ).scalars().all()
        grouped: dict[str, list[Event]] = defaultdict(list)
        for event in events:
            grouped[event.event_type].append(event)

        existing_names = await _existing_candidate_names(session)
        created = 0
        for event_type, event_group in grouped.items():
            if len(event_group) < min_events:
                continue
            candidate_type = _categorize_event(event_group[0])
            name = _candidate_name(event_type)
            if name in existing_names:
                continue
            created_from_event_ids = [str(event.event_id) for event in event_group]
            summary = event_group[0].payload.get("summary") if event_group[0].payload else None
            domain = event_group[0].payload.get("domain") if event_group[0].payload else None
            tags = event_group[0].payload.get("tags") if event_group[0].payload else None
            description = summary or f"Auto-generated candidate from {event_type} events."
            if candidate_type == "skill":
                spec: dict[str, Any] = {
                    "domain": domain,
                    "tags": tags or [],
                    "created_from_event_ids": created_from_event_ids,
                    "summary": summary,
                }
                await create_skill(
                    session,
                    name=name,
                    description=description,
                    spec=spec,
                    status=RegistryStatus.CANDIDATE,
                )
            else:
                config: dict[str, Any] = {
                    "domain": domain,
                    "tags": tags or [],
                    "created_from_event_ids": created_from_event_ids,
                    "summary": summary,
                }
                await create_agent(
                    session,
                    name=name,
                    description=description,
                    config=config,
                    status=RegistryStatus.CANDIDATE,
                )
            created += 1
        return {"created": created}


@celery_app.task
def consolidate_candidates() -> dict[str, int]:
    result = asyncio.run(_consolidate_candidates())
    logger.info("Consolidated candidates: %s", result)
    return result
