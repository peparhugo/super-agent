from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.retrieval import MemoryPointer, hybrid_retrieval
from app.models import Agent, RegistryStatus


@dataclass(frozen=True)
class RoutedRequest:
    agent_template: dict
    agent_metadata: dict
    skill_pointers: list[MemoryPointer]
    memory_pointers: list[MemoryPointer]


def _filter_by_tags(candidate_tags: Iterable[str] | None, required: set[str]) -> bool:
    if not required:
        return True
    if not candidate_tags:
        return False
    normalized = {tag.strip().lower() for tag in candidate_tags if tag.strip()}
    return required.issubset(normalized)


async def _select_agent_template(
    session: AsyncSession,
    *,
    statuses: Sequence[RegistryStatus],
    tags: Iterable[str] | None,
    domain: str | None,
    since: datetime.datetime | None,
) -> tuple[dict, dict]:
    query = select(Agent).where(Agent.status.in_(statuses))
    if since is not None:
        query = query.where(Agent.created_at >= since)
    query = query.order_by(Agent.version.desc(), Agent.created_at.desc())
    agents = (await session.execute(query)).scalars().all()

    required_tags = {tag.strip().lower() for tag in tags or [] if tag.strip()}
    for agent in agents:
        config = agent.config or {}
        if domain and config.get("domain") != domain:
            continue
        if not _filter_by_tags(config.get("tags"), required_tags):
            continue
        template = config.get("template") or config
        metadata = {
            "agent_id": str(agent.agent_id),
            "name": agent.name,
            "version": agent.version,
            "status": agent.status.value,
            "domain": config.get("domain"),
            "tags": config.get("tags"),
        }
        return template, metadata

    return {}, {}


async def route_request(
    session: AsyncSession,
    *,
    query_embedding: list[float],
    statuses: Sequence[RegistryStatus] = (RegistryStatus.ACTIVE,),
    tags: Iterable[str] | None = None,
    domain: str | None = None,
    since: datetime.datetime | None = None,
    memory_limit: int = 6,
    skill_limit: int = 6,
) -> RoutedRequest:
    agent_template, agent_metadata = await _select_agent_template(
        session,
        statuses=statuses,
        tags=tags,
        domain=domain,
        since=since,
    )
    skill_pointers, memory_pointers = await hybrid_retrieval(
        session,
        query_embedding=query_embedding,
        memory_limit=memory_limit,
        skill_limit=skill_limit,
        statuses=statuses,
        tags=tags,
        domain=domain,
        since=since,
    )
    return RoutedRequest(
        agent_template=agent_template,
        agent_metadata=agent_metadata,
        skill_pointers=skill_pointers,
        memory_pointers=memory_pointers,
    )
