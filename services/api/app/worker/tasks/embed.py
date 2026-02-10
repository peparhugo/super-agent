from __future__ import annotations

import asyncio
import datetime
import os
from collections.abc import Iterable

import httpx
from celery.utils.log import get_task_logger
from qdrant_client.http import models as qdrant_models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.memory.index import ensure_collection, get_qdrant_client
from app.models import Agent, Event, Skill
from app.settings import get_settings
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)


def _event_to_text(event: Event) -> str:
    payload = event.payload or {}
    summary = payload.get("summary") or payload.get("message") or ""
    return f"{event.event_type} {summary}".strip()


def _skill_to_text(skill: Skill) -> str:
    return f"{skill.name} {skill.description or ''}".strip()


def _agent_to_text(agent: Agent) -> str:
    return f"{agent.name} {agent.description or ''}".strip()


async def _embed_texts(texts: Iterable[str]) -> list[list[float]]:
    settings = get_settings()
    request_body = {"model": settings.embedding_model, "input": list(texts)}
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=60) as client:
        response = await client.post("/v1/embeddings", json=request_body, headers=headers)
        response.raise_for_status()
        data = response.json()
    embeddings = [item.get("embedding") for item in data.get("data", [])]
    if any(embedding is None for embedding in embeddings):
        raise RuntimeError("Embedding service returned missing vectors")
    return [list(embedding) for embedding in embeddings]


async def _gather_items(session: AsyncSession) -> tuple[list[Event], list[Skill], list[Agent]]:
    lookback_hours = float(os.getenv("EMBED_LOOKBACK_HOURS", "24"))
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=lookback_hours)
    events = (
        await session.execute(select(Event).where(Event.created_at >= since))
    ).scalars().all()
    skills = (
        await session.execute(select(Skill).where(Skill.created_at >= since))
    ).scalars().all()
    agents = (
        await session.execute(select(Agent).where(Agent.created_at >= since))
    ).scalars().all()
    return events, skills, agents


async def _upsert_vectors(session: AsyncSession) -> dict[str, int]:
    events, skills, agents = await _gather_items(session)
    texts: list[str] = []
    payloads: list[dict] = []
    ids: list[str] = []

    for event in events:
        text = _event_to_text(event)
        if not text:
            continue
        payload = event.payload or {}
        ids.append(str(event.event_id))
        texts.append(text)
        payloads.append(
            {
                "item_type": "memory",
                "item_id": str(event.event_id),
                "title": event.event_type,
                "domain": payload.get("domain"),
                "tags": payload.get("tags") or [],
                "status": "logged",
                "created_at": event.created_at.timestamp(),
                "snippet": payload.get("summary") or payload.get("message") or "",
            }
        )

    for skill in skills:
        text = _skill_to_text(skill)
        if not text:
            continue
        spec = skill.spec or {}
        ids.append(str(skill.skill_id))
        texts.append(text)
        payloads.append(
            {
                "item_type": "skill",
                "item_id": str(skill.skill_id),
                "title": skill.name,
                "domain": spec.get("domain"),
                "tags": spec.get("tags") or [],
                "status": str(skill.status),
                "created_at": skill.created_at.timestamp(),
                "snippet": skill.description or "",
            }
        )

    for agent in agents:
        text = _agent_to_text(agent)
        if not text:
            continue
        config = agent.config or {}
        ids.append(str(agent.agent_id))
        texts.append(text)
        payloads.append(
            {
                "item_type": "agent",
                "item_id": str(agent.agent_id),
                "title": agent.name,
                "domain": config.get("domain"),
                "tags": config.get("tags") or [],
                "status": str(agent.status),
                "created_at": agent.created_at.timestamp(),
                "snippet": agent.description or "",
            }
        )

    if not texts:
        return {"events": 0, "skills": 0, "agents": 0}

    embeddings = await _embed_texts(texts)
    qdrant_client = get_qdrant_client()
    collection = ensure_collection(qdrant_client).name

    points = [
        qdrant_models.PointStruct(id=ids[idx], vector=embeddings[idx], payload=payloads[idx])
        for idx in range(len(ids))
    ]
    qdrant_client.upsert(collection_name=collection, points=points)
    return {
        "events": len(events),
        "skills": len(skills),
        "agents": len(agents),
    }


@celery_app.task
def embed_new_items() -> dict[str, int]:
    async def _runner() -> dict[str, int]:
        session_factory = get_sessionmaker(role="worker")
        async with session_factory() as session:
            return await _upsert_vectors(session)

    result = asyncio.run(_runner())
    logger.info("Embedded items: %s", result)
    return result
