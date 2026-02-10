from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import AuthorizationError, authorize_memory_access, normalize_risk, normalize_role
from app.memory.retrieval import MemoryPointer, hybrid_retrieval
from app.models import Agent, RegistryStatus
from app.settings import Settings

logger = logging.getLogger(__name__)


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
    settings: Settings,
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
    agent_role = normalize_role(
        agent_template.get("role") or agent_template.get("agent_role") or agent_metadata.get("role")
    )
    agent_risk = normalize_risk(agent_template.get("risk_level") or agent_template.get("risk"))
    skill_pointers = await _filter_memory_pointers(
        settings,
        agent_role=agent_role,
        agent_risk=agent_risk,
        pointers=skill_pointers,
        source="skill_retrieval",
    )
    memory_pointers = await _filter_memory_pointers(
        settings,
        agent_role=agent_role,
        agent_risk=agent_risk,
        pointers=memory_pointers,
        source="memory_retrieval",
    )
    return RoutedRequest(
        agent_template=agent_template,
        agent_metadata=agent_metadata,
        skill_pointers=skill_pointers,
        memory_pointers=memory_pointers,
    )


async def _filter_memory_pointers(
    settings: Settings,
    *,
    agent_role: str,
    agent_risk: str,
    pointers: list[MemoryPointer],
    source: str,
) -> list[MemoryPointer]:
    allowed: list[MemoryPointer] = []
    for pointer in pointers:
        try:
            decision = await authorize_memory_access(
                settings,
                agent_role=agent_role,
                agent_risk_level=agent_risk,
                memory_risk_level=pointer.metadata.get("risk_level"),
                memory_type=pointer.item_type,
                source=source,
                contains_instruction=bool(pointer.metadata.get("contains_instruction")),
                tags=pointer.metadata.get("tags"),
            )
            if decision.allowed:
                allowed.append(pointer)
        except AuthorizationError as exc:
            logger.warning("Memory authorization failed for %s: %s", pointer.item_id, exc)
    return allowed
