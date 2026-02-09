from __future__ import annotations

import datetime
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Event, RegistryStatus
from app.registry.agents import create_agent, get_agent, transition_agent_status
from app.registry.skills import create_skill, get_skill, transition_skill_status
from app.runtime.planner import PlannerClient
from app.runtime.prompt_compiler import PromptInputs, compile_prompt
from app.runtime.router import RoutedRequest, route_request
from app.runtime.verifier import VerifierClient
from app.settings import Settings, get_settings

app = FastAPI(title="Super Agent API")


class ChatRequest(BaseModel):
    message: str
    tags: list[str] | None = None
    domain: str | None = None
    since: datetime.datetime | None = None
    memory_limit: int = 6
    skill_limit: int = 6
    statuses: list[RegistryStatus] | None = None


class PlanStepResponse(BaseModel):
    step_id: str
    description: str
    tool: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class VerificationResponse(BaseModel):
    passed: bool
    fixes: list[str] = Field(default_factory=list)
    notes: str | None = None


class ChatResponse(BaseModel):
    response: str
    plan: list[PlanStepResponse]
    verification: VerificationResponse
    agent: dict
    routing: dict


class AgentCreateRequest(BaseModel):
    name: str
    description: str | None = None
    config: dict = Field(default_factory=dict)
    version: int | None = None
    status: RegistryStatus = RegistryStatus.DRAFT


class SkillCreateRequest(BaseModel):
    name: str
    description: str | None = None
    spec: dict = Field(default_factory=dict)
    version: int | None = None
    status: RegistryStatus = RegistryStatus.DRAFT


class StatusTransitionRequest(BaseModel):
    status: RegistryStatus


class IntrospectionResponse(BaseModel):
    llm_base_url: str
    planner_model: str
    verifier_model: str
    chat_model: str
    embedding_model: str
    temperature: float
    max_tokens: int


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    await _log_event(session, "chat.request", {"message": payload.message})
    embedding = await _embed_query(payload.message, settings)
    routed = await _route(session, payload, embedding)
    planner = PlannerClient(settings)
    plan = await planner.create_plan(
        user_input=payload.message,
        agent_template=routed.agent_template,
        skill_pointers=routed.skill_pointers,
        memory_pointers=routed.memory_pointers,
    )
    output = await _act(settings, payload.message, routed)
    verifier = VerifierClient(settings)
    verification = await verifier.verify(
        plan={"steps": [step.__dict__ for step in plan.steps], "notes": plan.notes},
        output=output,
        schema={"response": "string"},
        policy={"follow_agent_template": True, "cite_memory": True},
        evidence={
            "agent": routed.agent_metadata,
            "skills": [pointer.metadata for pointer in routed.skill_pointers],
            "memory": [pointer.metadata for pointer in routed.memory_pointers],
        },
    )
    response_payload = {
        "response": output,
        "plan": [PlanStepResponse(**step.__dict__) for step in plan.steps],
        "verification": VerificationResponse(**verification.__dict__),
        "agent": routed.agent_metadata,
        "routing": {
            "skill_count": len(routed.skill_pointers),
            "memory_count": len(routed.memory_pointers),
        },
    }
    await _log_event(
        session,
        "chat.response",
        {
            "response": output,
            "plan": [step.__dict__ for step in plan.steps],
            "verification": verification.__dict__,
            "agent": routed.agent_metadata,
        },
    )
    return ChatResponse(**response_payload)


@app.post("/agents")
async def create_agent_endpoint(
    payload: AgentCreateRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    agent = await create_agent(
        session,
        name=payload.name,
        description=payload.description,
        config=payload.config,
        version=payload.version,
        status=payload.status,
    )
    return {"agent_id": str(agent.agent_id), "version": agent.version}


@app.get("/agents/{name}/{version}")
async def get_agent_endpoint(
    name: str, version: int, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    agent = await get_agent(session, name=name, version=version)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {
        "agent_id": str(agent.agent_id),
        "name": agent.name,
        "version": agent.version,
        "status": agent.status,
        "description": agent.description,
        "config": agent.config,
    }


@app.post("/agents/{agent_id}/status")
async def transition_agent_status_endpoint(
    agent_id: str,
    payload: StatusTransitionRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    agent = await transition_agent_status(session, agent_id=agent_id, new_status=payload.status)
    return {"agent_id": str(agent.agent_id), "status": agent.status}


@app.post("/skills")
async def create_skill_endpoint(
    payload: SkillCreateRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    skill = await create_skill(
        session,
        name=payload.name,
        description=payload.description,
        spec=payload.spec,
        version=payload.version,
        status=payload.status,
    )
    return {"skill_id": str(skill.skill_id), "version": skill.version}


@app.get("/skills/{name}/{version}")
async def get_skill_endpoint(
    name: str, version: int, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    skill = await get_skill(session, name=name, version=version)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {
        "skill_id": str(skill.skill_id),
        "name": skill.name,
        "version": skill.version,
        "status": skill.status,
        "description": skill.description,
        "spec": skill.spec,
    }


@app.post("/skills/{skill_id}/status")
async def transition_skill_status_endpoint(
    skill_id: str,
    payload: StatusTransitionRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    skill = await transition_skill_status(session, skill_id=skill_id, new_status=payload.status)
    return {"skill_id": str(skill.skill_id), "status": skill.status}


@app.get("/introspect", response_model=IntrospectionResponse)
async def introspect(settings: Settings = Depends(get_settings)) -> IntrospectionResponse:
    return IntrospectionResponse(
        llm_base_url=settings.llm_base_url,
        planner_model=settings.planner_model,
        verifier_model=settings.verifier_model,
        chat_model=settings.chat_model,
        embedding_model=settings.embedding_model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )


async def _route(
    session: AsyncSession,
    payload: ChatRequest,
    embedding: list[float],
) -> RoutedRequest:
    statuses = payload.statuses or [RegistryStatus.ACTIVE]
    return await route_request(
        session,
        query_embedding=embedding,
        statuses=statuses,
        tags=payload.tags,
        domain=payload.domain,
        since=payload.since,
        memory_limit=payload.memory_limit,
        skill_limit=payload.skill_limit,
    )


async def _embed_query(message: str, settings: Settings) -> list[float]:
    request_body = {"model": settings.embedding_model, "input": message}
    if settings.llm_api_key:
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    else:
        headers = {}
    async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=60) as client:
        response = await client.post("/v1/embeddings", json=request_body, headers=headers)
        response.raise_for_status()
        data = response.json()
    embedding = data.get("data", [{}])[0].get("embedding")
    if not embedding:
        raise HTTPException(status_code=502, detail="Embedding service returned no data")
    return list(embedding)


async def _act(
    settings: Settings,
    message: str,
    routed: RoutedRequest,
) -> str:
    system_preamble = "You are a helpful assistant. Follow the agent template precisely."
    prompt = compile_prompt(
        PromptInputs(
            system_preamble=system_preamble,
            agent_template=routed.agent_template,
            user_input=message,
            skill_pointers=routed.skill_pointers,
            memory_pointers=routed.memory_pointers,
        )
    )
    payload = {
        "model": settings.chat_model,
        "temperature": settings.temperature,
        "max_tokens": settings.chat_max_tokens,
        "messages": [
            {"role": "system", "content": system_preamble},
            {"role": "user", "content": prompt},
        ],
    }
    if settings.llm_api_key:
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    else:
        headers = {}
    async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=90) as client:
        response = await client.post("/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""


async def _log_event(session: AsyncSession, event_type: str, payload: dict) -> None:
    session.add(Event(event_type=event_type, payload=payload))
    await session.commit()
