from __future__ import annotations

import asyncio

from celery.utils.log import get_task_logger

from app.memory.ingest import run_ingestion_cycle
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task
def ingest_knowledge_documents() -> dict[str, int]:
    result = asyncio.run(run_ingestion_cycle())
    logger.info("Ingested knowledge documents: %s", result)
    return result
