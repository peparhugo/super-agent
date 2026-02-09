from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Iterable, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.index import ensure_collection, get_qdrant_client
from app.models import Agent, RegistryStatus, Skill


@dataclass(frozen=True)
class MemoryPointer:
    item_id: str
    item_type: str
    score: float
    metadata: dict


def _normalize_tags(tags: Iterable[str] | None) -> set[str]:
    if not tags:
        return set()
    return {tag.strip().lower() for tag in tags if tag.strip()}


def _passes_tag_filter(candidate_tags: Iterable[str] | None, required: set[str]) -> bool:
    if not required:
        return True
    if not candidate_tags:
        return False
    normalized = {tag.strip().lower() for tag in candidate_tags if tag.strip()}
    return required.issubset(normalized)


async def _load_registry_ids(
    session: AsyncSession,
    *,
    statuses: Sequence[RegistryStatus],
    tags: Iterable[str] | None,
    domain: str | None,
    since: datetime.datetime | None,
    item_types: Iterable[str],
) -> set[str]:
    allowed_ids: set[str] = set()
    tag_filter = _normalize_tags(tags)

    if "agent" in item_types:
        query = select(Agent).where(Agent.status.in_(statuses))
        if since is not None:
            query = query.where(Agent.created_at >= since)
        agents = (await session.execute(query)).scalars().all()
        for agent in agents:
            config = agent.config or {}
            if domain and config.get("domain") != domain:
                continue
            if not _passes_tag_filter(config.get("tags"), tag_filter):
                continue
            allowed_ids.add(str(agent.agent_id))

    if "skill" in item_types:
        query = select(Skill).where(Skill.status.in_(statuses))
        if since is not None:
            query = query.where(Skill.created_at >= since)
        skills = (await session.execute(query)).scalars().all()
        for skill in skills:
            spec = skill.spec or {}
            if domain and spec.get("domain") != domain:
                continue
            if not _passes_tag_filter(spec.get("tags"), tag_filter):
                continue
            allowed_ids.add(str(skill.skill_id))

    return allowed_ids


def _build_qdrant_filter(
    *,
    tags: Iterable[str] | None,
    domain: str | None,
    item_types: Iterable[str] | None,
    since: datetime.datetime | None,
) -> qdrant_models.Filter | None:
    conditions: list[qdrant_models.FieldCondition] = []
    if domain:
        conditions.append(
            qdrant_models.FieldCondition(
                key="domain", match=qdrant_models.MatchValue(value=domain)
            )
        )
    normalized_tags = _normalize_tags(tags)
    for tag in normalized_tags:
        conditions.append(
            qdrant_models.FieldCondition(
                key="tags", match=qdrant_models.MatchValue(value=tag)
            )
        )
    if item_types:
        conditions.append(
            qdrant_models.FieldCondition(
                key="item_type",
                match=qdrant_models.MatchAny(any=list(item_types)),
            )
        )
    if since is not None:
        conditions.append(
            qdrant_models.FieldCondition(
                key="created_at",
                range=qdrant_models.Range(gte=since.timestamp()),
            )
        )
    if not conditions:
        return None
    return qdrant_models.Filter(must=conditions)


def _payload_to_pointer(
    point: qdrant_models.ScoredPoint,
) -> MemoryPointer:
    payload = point.payload or {}
    item_type = payload.get("item_type", "memory")
    item_id = payload.get("item_id") or str(point.id)
    minimal_metadata = {
        key: payload.get(key)
        for key in ("title", "domain", "tags", "risk_level", "status", "snippet")
        if payload.get(key) is not None
    }
    return MemoryPointer(
        item_id=str(item_id),
        item_type=str(item_type),
        score=float(point.score or 0.0),
        metadata=minimal_metadata,
    )


async def retrieve_semantic(
    session: AsyncSession,
    *,
    query_embedding: list[float],
    limit: int = 8,
    statuses: Sequence[RegistryStatus] = (RegistryStatus.ACTIVE,),
    tags: Iterable[str] | None = None,
    domain: str | None = None,
    since: datetime.datetime | None = None,
    item_types: Iterable[str] | None = None,
    client: QdrantClient | None = None,
) -> list[MemoryPointer]:
    qdrant_client = client or get_qdrant_client()
    collection = ensure_collection(qdrant_client).name

    item_types = list(item_types or [])
    registry_ids: set[str] = set()
    if item_types:
        registry_ids = await _load_registry_ids(
            session,
            statuses=statuses,
            tags=tags,
            domain=domain,
            since=since,
            item_types=item_types,
        )

    qdrant_filter = _build_qdrant_filter(
        tags=tags,
        domain=domain,
        item_types=item_types or None,
        since=since,
    )
    results = qdrant_client.search(
        collection_name=collection,
        query_vector=query_embedding,
        limit=limit * 3,
        with_payload=True,
        query_filter=qdrant_filter,
    )

    pointers: list[MemoryPointer] = []
    for scored_point in results:
        payload = scored_point.payload or {}
        item_id = str(payload.get("item_id") or scored_point.id)
        if registry_ids and item_id not in registry_ids:
            continue
        pointer = _payload_to_pointer(scored_point)
        pointers.append(pointer)
        if len(pointers) >= limit:
            break
    return pointers


async def hybrid_retrieval(
    session: AsyncSession,
    *,
    query_embedding: list[float],
    memory_limit: int = 6,
    skill_limit: int = 6,
    statuses: Sequence[RegistryStatus] = (RegistryStatus.ACTIVE,),
    tags: Iterable[str] | None = None,
    domain: str | None = None,
    since: datetime.datetime | None = None,
    client: QdrantClient | None = None,
) -> tuple[list[MemoryPointer], list[MemoryPointer]]:
    skill_pointers = await retrieve_semantic(
        session,
        query_embedding=query_embedding,
        limit=skill_limit,
        statuses=statuses,
        tags=tags,
        domain=domain,
        since=since,
        item_types=["skill"],
        client=client,
    )
    memory_pointers = await retrieve_semantic(
        session,
        query_embedding=query_embedding,
        limit=memory_limit,
        statuses=statuses,
        tags=tags,
        domain=domain,
        since=since,
        item_types=["memory"],
        client=client,
    )
    return skill_pointers, memory_pointers
