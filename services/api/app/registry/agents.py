from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, RegistryStatus

_AGENT_TRANSITIONS: dict[RegistryStatus, set[RegistryStatus]] = {
    RegistryStatus.DRAFT: {RegistryStatus.CANDIDATE},
    RegistryStatus.CANDIDATE: {RegistryStatus.ACTIVE, RegistryStatus.DEPRECATED},
    RegistryStatus.ACTIVE: {RegistryStatus.DEPRECATED},
    RegistryStatus.DEPRECATED: set(),
}


async def create_agent(
    session: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    config: dict | None = None,
    version: int | None = None,
    status: RegistryStatus = RegistryStatus.DRAFT,
) -> Agent:
    if version is None:
        latest_version = await session.scalar(
            select(func.max(Agent.version)).where(Agent.name == name)
        )
        version = (latest_version or 0) + 1
    agent = Agent(
        name=name,
        version=version,
        status=status,
        description=description,
        config=config or {},
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


async def get_agent(session: AsyncSession, *, name: str, version: int) -> Agent | None:
    result = await session.execute(
        select(Agent).where(Agent.name == name, Agent.version == version)
    )
    return result.scalar_one_or_none()


async def transition_agent_status(
    session: AsyncSession,
    *,
    agent_id: str,
    new_status: RegistryStatus,
) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")
    if new_status not in _AGENT_TRANSITIONS[agent.status]:
        raise ValueError(f"Invalid status transition {agent.status} -> {new_status}")
    await session.execute(
        update(Agent).where(Agent.agent_id == agent.agent_id).values(status=new_status)
    )
    await session.commit()
    await session.refresh(agent)
    return agent
