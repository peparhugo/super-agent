from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RegistryStatus, Skill

_SKILL_TRANSITIONS: dict[RegistryStatus, set[RegistryStatus]] = {
    RegistryStatus.DRAFT: {RegistryStatus.CANDIDATE},
    RegistryStatus.CANDIDATE: {RegistryStatus.ACTIVE, RegistryStatus.DEPRECATED},
    RegistryStatus.ACTIVE: {RegistryStatus.DEPRECATED},
    RegistryStatus.DEPRECATED: set(),
}


async def create_skill(
    session: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    spec: dict | None = None,
    version: int | None = None,
    status: RegistryStatus = RegistryStatus.DRAFT,
) -> Skill:
    if version is None:
        latest_version = await session.scalar(
            select(func.max(Skill.version)).where(Skill.name == name)
        )
        version = (latest_version or 0) + 1
    skill = Skill(
        name=name,
        version=version,
        status=status,
        description=description,
        spec=spec or {},
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return skill


async def get_skill(session: AsyncSession, *, name: str, version: int) -> Skill | None:
    result = await session.execute(
        select(Skill).where(Skill.name == name, Skill.version == version)
    )
    return result.scalar_one_or_none()


async def transition_skill_status(
    session: AsyncSession,
    *,
    skill_id: str,
    new_status: RegistryStatus,
) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise ValueError(f"Skill {skill_id} not found")
    if new_status not in _SKILL_TRANSITIONS[skill.status]:
        raise ValueError(f"Invalid status transition {skill.status} -> {new_status}")
    await session.execute(
        update(Skill).where(Skill.skill_id == skill.skill_id).values(status=new_status)
    )
    await session.commit()
    await session.refresh(skill)
    return skill
