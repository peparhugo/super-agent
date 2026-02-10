from __future__ import annotations

import asyncio
import datetime
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from celery.utils.log import get_task_logger
from qdrant_client.http import models as qdrant_models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.memory.events import append_event
from app.memory.index import ensure_collection, get_qdrant_client
from app.models import KnowledgeDocument
from app.settings import get_settings

logger = get_task_logger(__name__)

TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv"}


@dataclass(frozen=True)
class KnowledgeFile:
    source_path: str
    domain: str
    checksum: str
    content: str


def _knowledge_root() -> Path:
    return Path(os.getenv("KNOWLEDGE_ROOT", "knowledge")).resolve()


def _extract_domain(root: Path, file_path: Path) -> str:
    try:
        relative = file_path.relative_to(root)
    except ValueError:
        return "shared"
    return relative.parts[0] if relative.parts else "shared"


def _is_supported_document(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def discover_knowledge_files() -> list[KnowledgeFile]:
    root = _knowledge_root()
    if not root.exists():
        return []

    max_chars = int(os.getenv("KNOWLEDGE_INGEST_MAX_CHARS", "16000"))
    discovered: list[KnowledgeFile] = []
    for path in root.rglob("*"):
        if not path.is_file() or not _is_supported_document(path):
            continue
        relative_path = str(path.relative_to(root))
        content = path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        discovered.append(
            KnowledgeFile(
                source_path=relative_path,
                domain=_extract_domain(root, path),
                checksum=checksum,
                content=content,
            )
        )
    return discovered


async def _summarize_document(content: str) -> str:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    prompt = (
        "Summarize the following document in 4-6 concise bullet points. "
        "Include key entities, decisions, and any risks. Keep under 120 words.\n\n"
        f"Document:\n{content}"
    )
    body = {
        "model": settings.chat_model,
        "messages": [
            {"role": "system", "content": "You produce compact operational summaries."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": min(settings.chat_max_tokens, 250),
    }
    async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=60) as client:
        response = await client.post("/v1/chat/completions", json=body, headers=headers)
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"].strip()


async def _embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    request_body = {"model": settings.embedding_model, "input": texts}
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=60) as client:
        response = await client.post("/v1/embeddings", json=request_body, headers=headers)
        response.raise_for_status()
        data = response.json()
    embeddings = [item.get("embedding") for item in data.get("data", [])]
    if any(embedding is None for embedding in embeddings):
        raise RuntimeError("Embedding service returned missing vectors")
    return [list(embedding) for embedding in embeddings]


async def _register_discovered_files(
    session: AsyncSession,
    files: list[KnowledgeFile],
) -> tuple[int, list[KnowledgeDocument]]:
    discovered_count = 0
    changed_documents: list[KnowledgeDocument] = []

    for item in files:
        existing = (
            await session.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.source_path == item.source_path)
            )
        ).scalar_one_or_none()
        if existing is None:
            doc = KnowledgeDocument(
                source_path=item.source_path,
                source="filesystem",
                domain=item.domain,
                checksum=item.checksum,
                status="discovered",
                metadata={"ingested_at": datetime.datetime.utcnow().isoformat()},
            )
            session.add(doc)
            discovered_count += 1
            changed_documents.append(doc)
        elif existing.checksum != item.checksum:
            existing.checksum = item.checksum
            existing.domain = item.domain
            existing.status = "discovered"
            existing.summary = None
            existing.metadata = {
                **(existing.metadata or {}),
                "reingested_at": datetime.datetime.utcnow().isoformat(),
            }
            discovered_count += 1
            changed_documents.append(existing)

    await session.commit()

    for doc in changed_documents:
        await append_event(
            session,
            event_type="knowledge.document.discovered",
            source="knowledge_ingest",
            payload={
                "source": doc.source_path,
                "domain": doc.domain,
                "date": datetime.datetime.utcnow().date().isoformat(),
            },
        )

    refreshed_docs = (
        await session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.status == "discovered")
        )
    ).scalars().all()
    return discovered_count, list(refreshed_docs)


async def _summarize_and_upsert(
    session: AsyncSession,
    pending_documents: list[KnowledgeDocument],
) -> int:
    if not pending_documents:
        return 0

    root = _knowledge_root()
    summaries: list[str] = []
    payloads: list[dict] = []
    ids: list[str] = []

    for doc in pending_documents:
        source_file = root / doc.source_path
        if not source_file.exists():
            doc.status = "missing"
            continue

        content = source_file.read_text(encoding="utf-8", errors="ignore")
        summary = await _summarize_document(content)
        doc.summary = summary
        doc.status = "summarized"
        doc.summarized_at = datetime.datetime.utcnow()

        await append_event(
            session,
            event_type="knowledge.document.summarized",
            source="knowledge_ingest",
            payload={
                "source": doc.source_path,
                "domain": doc.domain,
                "date": datetime.datetime.utcnow().date().isoformat(),
                "summary": summary,
            },
        )

        ids.append(str(doc.document_id))
        summaries.append(summary)
        payloads.append(
            {
                "item_type": "knowledge_summary",
                "item_id": str(doc.document_id),
                "source_id": doc.source_path,
                "source": doc.source,
                "domain": doc.domain,
                "created_at": datetime.datetime.utcnow().timestamp(),
                "date": datetime.datetime.utcnow().date().isoformat(),
                "snippet": summary,
                "title": doc.source_path,
                "status": doc.status,
            }
        )

    await session.commit()

    if not summaries:
        return 0

    embeddings = await _embed_texts(summaries)
    qdrant_client = get_qdrant_client()
    collection = ensure_collection(qdrant_client).name
    points = [
        qdrant_models.PointStruct(id=ids[idx], vector=embeddings[idx], payload=payloads[idx])
        for idx in range(len(ids))
    ]
    qdrant_client.upsert(collection_name=collection, points=points)
    return len(points)


async def run_ingestion_cycle() -> dict[str, int]:
    files = discover_knowledge_files()
    session_factory = get_sessionmaker(role="worker")
    async with session_factory() as session:
        discovered_count, pending_documents = await _register_discovered_files(session, files)
        indexed_count = await _summarize_and_upsert(session, pending_documents)

    result = {
        "documents_seen": len(files),
        "documents_discovered": discovered_count,
        "summaries_indexed": indexed_count,
    }
    logger.info("Knowledge ingestion cycle completed: %s", result)
    return result


def run_watcher(interval_seconds: float = 30.0) -> None:
    logger.info("Starting knowledge watcher interval=%s", interval_seconds)
    while True:
        asyncio.run(run_ingestion_cycle())
        time.sleep(interval_seconds)


if __name__ == "__main__":
    once = os.getenv("KNOWLEDGE_WATCH_ONCE", "false").lower() == "true"
    if once:
        asyncio.run(run_ingestion_cycle())
    else:
        run_watcher(float(os.getenv("KNOWLEDGE_WATCH_INTERVAL_SECONDS", "30")))
