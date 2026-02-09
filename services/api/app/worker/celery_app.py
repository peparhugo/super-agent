import os

from celery import Celery

celery_app = Celery("super_agent")
celery_app.conf.broker_url = os.getenv("REDIS_BROKER_URL", "redis://redis:6379/0")
celery_app.conf.result_backend = os.getenv("REDIS_RESULT_BACKEND", "redis://redis:6379/1")


@celery_app.task
def ping() -> str:
    return "pong"
