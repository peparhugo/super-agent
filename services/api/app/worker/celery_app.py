import os

from celery import Celery
from celery.schedules import crontab

celery_app = Celery("super_agent")
celery_app.conf.update(
    broker_url=os.getenv("REDIS_BROKER_URL", "redis://redis:6379/0"),
    result_backend=os.getenv("REDIS_RESULT_BACKEND", "redis://redis:6379/1"),
    timezone=os.getenv("CELERY_TIMEZONE", "UTC"),
    enable_utc=True,
    beat_schedule={
        "embed-new-items": {
            "task": "app.worker.tasks.embed.embed_new_items",
            "schedule": float(os.getenv("EMBED_SCHEDULE_SECONDS", "300")),
        },
        "ingest-knowledge-documents": {
            "task": "app.worker.tasks.ingest.ingest_knowledge_documents",
            "schedule": float(os.getenv("KNOWLEDGE_INGEST_SCHEDULE_SECONDS", "180")),
        },
        "consolidate-candidates": {
            "task": "app.worker.tasks.consolidate.consolidate_candidates",
            "schedule": crontab(minute="*/10"),
        },
        "run-evaluations": {
            "task": "app.worker.tasks.evaluate.evaluate_candidates",
            "schedule": crontab(minute="*/15"),
        },
        "generate-curriculum": {
            "task": "app.worker.tasks.curriculum.generate_curriculum",
            "schedule": crontab(hour="*/6"),
        },
    },
)
celery_app.autodiscover_tasks(["app.worker"])


@celery_app.task
def ping() -> str:
    return "pong"
