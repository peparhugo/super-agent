from __future__ import annotations

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event


async def append_event(
    session: AsyncSession,
    *,
    event_type: str,
    source: str | None = None,
    payload: dict | None = None,
) -> str:
    statement = (
        insert(Event)
        .values(event_type=event_type, source=source, payload=payload or {})
        .returning(Event.event_id)
    )
    result = await session.execute(statement)
    event_id = result.scalar_one()
    await session.commit()
    return str(event_id)
