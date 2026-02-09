from __future__ import annotations

import os
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Literal

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import Base

Role = Literal["runtime", "worker"]


def _resolve_database_url(role: Role) -> str:
    default_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/super_agent")
    if role == "worker":
        return os.getenv("WORKER_DATABASE_URL", default_url)
    return os.getenv("RUNTIME_DATABASE_URL", default_url)


@lru_cache(maxsize=2)
def get_engine(role: Role = "runtime") -> AsyncEngine:
    return create_async_engine(_resolve_database_url(role), pool_pre_ping=True)


@lru_cache(maxsize=2)
def get_sessionmaker(role: Role = "runtime") -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(role), expire_on_commit=False)


async def get_session(role: Role = "runtime") -> AsyncIterator[AsyncSession]:
    session_factory = get_sessionmaker(role)
    async with session_factory() as session:
        yield session


async def init_models(role: Role = "runtime") -> None:
    engine = get_engine(role)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
