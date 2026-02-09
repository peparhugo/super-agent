from __future__ import annotations

import os
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models


@dataclass(frozen=True)
class QdrantCollectionConfig:
    name: str
    vector_size: int
    distance: qdrant_models.Distance = qdrant_models.Distance.COSINE


METADATA_CONVENTIONS: dict[str, str] = {
    "item_type": "Category for the vector (agent, skill, memory, doc, etc.).",
    "item_id": "Primary identifier for the entity stored in Postgres or registry.",
    "source_id": "Upstream identifier (file ID, URL hash, etc.).",
    "domain": "Business or product domain used for routing and filtering.",
    "tags": "List of tags for topical filtering.",
    "risk_level": "Low/medium/high (or numeric) risk label for retrieved content.",
    "status": "Registry status string mirrored from Postgres.",
    "created_at": "Unix timestamp (seconds) for recency filtering.",
    "snippet": "Short excerpt or summary for prompt assembly.",
    "title": "Human-readable name for UI display.",
}


def get_qdrant_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    if url:
        return QdrantClient(url=url, api_key=api_key)
    host = os.getenv("QDRANT_HOST", "qdrant")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return QdrantClient(host=host, port=port, api_key=api_key)


def resolve_collection_config() -> QdrantCollectionConfig:
    name = os.getenv("QDRANT_COLLECTION", "super_agent_memory")
    vector_size = int(os.getenv("QDRANT_VECTOR_SIZE", "1536"))
    return QdrantCollectionConfig(name=name, vector_size=vector_size)


def ensure_collection(
    client: QdrantClient,
    *,
    config: QdrantCollectionConfig | None = None,
) -> QdrantCollectionConfig:
    config = config or resolve_collection_config()
    existing = client.get_collections().collections
    if not any(collection.name == config.name for collection in existing):
        client.create_collection(
            collection_name=config.name,
            vectors_config=qdrant_models.VectorParams(
                size=config.vector_size, distance=config.distance
            ),
        )
    payload_indexes = {
        "item_type": qdrant_models.PayloadSchemaType.KEYWORD,
        "item_id": qdrant_models.PayloadSchemaType.KEYWORD,
        "domain": qdrant_models.PayloadSchemaType.KEYWORD,
        "tags": qdrant_models.PayloadSchemaType.KEYWORD,
        "risk_level": qdrant_models.PayloadSchemaType.KEYWORD,
        "status": qdrant_models.PayloadSchemaType.KEYWORD,
        "created_at": qdrant_models.PayloadSchemaType.FLOAT,
    }
    for field, schema_type in payload_indexes.items():
        client.create_payload_index(
            collection_name=config.name,
            field_name=field,
            field_schema=schema_type,
        )
    return config
