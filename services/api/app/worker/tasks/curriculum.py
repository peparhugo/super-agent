from __future__ import annotations

import asyncio
import datetime
import os

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import Event
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)


def _is_failure(event: Event, confidence_threshold: float) -> bool:
    payload = event.payload or {}
    if payload.get("status") == "failed":
        return True
    confidence = payload.get("verification_confidence")
    if confidence is None:
        return False
    return float(confidence) < confidence_threshold


async def _generate_curriculum() -> dict[str, int]:
    lookback_hours = float(os.getenv("CURRICULUM_LOOKBACK_HOURS", "24"))
    confidence_threshold = float(os.getenv("CURRICULUM_CONFIDENCE_THRESHOLD", "0.6"))
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=lookback_hours)
    session_factory = get_sessionmaker(role="worker")
    async with session_factory() as session:
        events = (
            await session.execute(select(Event).where(Event.created_at >= since))
        ).scalars().all()
        existing_tasks = (
            await session.execute(
                select(Event).where(Event.event_type == "curriculum_task", Event.created_at >= since)
            )
        ).scalars().all()
        existing_source_ids = {
            (task.payload or {}).get("source_event_id") for task in existing_tasks
        }

        created = 0
        for event in events:
            if not _is_failure(event, confidence_threshold):
                continue
            if str(event.event_id) in existing_source_ids:
                continue
            payload = event.payload or {}
            task_payload = {
                "source_event_id": str(event.event_id),
                "domain": payload.get("domain"),
                "tags": payload.get("tags") or [],
                "prompt": payload.get("summary")
                or payload.get("message")
                or f"Investigate failure from {event.event_type}",
                "priority": payload.get("priority", "medium"),
            }
            session.add(Event(event_type="curriculum_task", payload=task_payload))
            created += 1
        await session.commit()
        return {"created": created}


@celery_app.task
def generate_curriculum() -> dict[str, int]:
    result = asyncio.run(_generate_curriculum())
    logger.info("Generated curriculum tasks: %s", result)
    return result
