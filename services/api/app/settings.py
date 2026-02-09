from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_api_key: str | None
    planner_model: str
    verifier_model: str
    chat_model: str
    embedding_model: str
    temperature: float
    max_tokens: int
    planner_max_tokens: int
    verifier_max_tokens: int
    chat_max_tokens: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:8001"),
        llm_api_key=os.getenv("LLM_API_KEY"),
        planner_model=os.getenv("PLANNER_MODEL", "gpt-4.1-mini"),
        verifier_model=os.getenv("VERIFIER_MODEL", "gpt-4.1-mini"),
        chat_model=os.getenv("CHAT_MODEL", "gpt-4.1"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1200")),
        planner_max_tokens=int(os.getenv("PLANNER_MAX_TOKENS", "800")),
        verifier_max_tokens=int(os.getenv("VERIFIER_MAX_TOKENS", "600")),
        chat_max_tokens=int(os.getenv("CHAT_MAX_TOKENS", "1200")),
    )
