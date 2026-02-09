FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY services/api/pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        sqlalchemy \
        asyncpg \
        qdrant-client \
        celery \
        minio \
        opa-client \
        pydantic \
        redis \
        python-dotenv \
        httpx \
        mcp \
        openai-agents

COPY services/api/app /app/app

CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=info"]
