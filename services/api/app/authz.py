from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from app.settings import Settings

logger = logging.getLogger(__name__)


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthzDecision:
    allowed: bool
    reasons: list[str]
    decision: dict[str, Any]


@dataclass(frozen=True)
class ExecutionProfile:
    profile: str
    docker_socket: bool
    filesystem: str


def normalize_role(role: str | None) -> str:
    return (role or "default").strip().lower() or "default"


def normalize_risk(risk_level: str | None) -> str:
    normalized = (risk_level or "low").strip().lower()
    if normalized in {"low", "medium", "high", "critical"}:
        return normalized
    return "low"


class OPAClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.opa_base_url.rstrip("/")
        self._timeout = settings.opa_timeout_s
        self._fail_open = settings.opa_fail_open

    async def query(self, policy_path: str, input_payload: dict[str, Any]) -> AuthzDecision:
        url = f"{self._base_url}/v1/data/{policy_path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json={"input": input_payload})
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            if self._fail_open:
                logger.warning("OPA request failed; allowing due to fail-open: %s", exc)
                return AuthzDecision(allowed=True, reasons=["opa_unavailable"], decision={})
            raise AuthorizationError(f"OPA request failed: {exc}") from exc

        result = data.get("result") or {}
        reasons = _normalize_reasons(result.get("reason"))
        return AuthzDecision(allowed=bool(result.get("allow", False)), reasons=reasons, decision=result)


def _normalize_reasons(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, set):
        return [str(item) for item in raw]
    return [str(raw)]


async def authorize_tool_access(
    settings: Settings,
    *,
    agent_role: str | None,
    agent_risk_level: str | None,
    tool_name: str,
    tool_risk_level: str | None,
    execution_profile: ExecutionProfile,
) -> AuthzDecision:
    client = OPAClient(settings)
    input_payload = {
        "agent": {
            "role": normalize_role(agent_role),
            "risk_level": normalize_risk(agent_risk_level),
        },
        "tool": {
            "name": tool_name,
            "risk_level": normalize_risk(tool_risk_level),
        },
        "execution": {
            "profile": execution_profile.profile,
            "docker_socket": execution_profile.docker_socket,
            "filesystem": execution_profile.filesystem,
        },
    }
    return await client.query("super_agent/tool_access", input_payload)


async def authorize_memory_access(
    settings: Settings,
    *,
    agent_role: str | None,
    agent_risk_level: str | None,
    memory_risk_level: str | None,
    memory_type: str,
    source: str,
    contains_instruction: bool,
    tags: Iterable[str] | None = None,
) -> AuthzDecision:
    client = OPAClient(settings)
    normalized_tags: list[str]
    if tags is None:
        normalized_tags = []
    elif isinstance(tags, str):
        normalized_tags = [tags]
    else:
        normalized_tags = [str(tag) for tag in tags]
    input_payload = {
        "agent": {
            "role": normalize_role(agent_role),
            "risk_level": normalize_risk(agent_risk_level),
        },
        "memory": {
            "risk_level": normalize_risk(memory_risk_level),
            "type": memory_type,
            "source": source,
            "contains_instruction": contains_instruction,
            "tags": normalized_tags,
        },
    }
    return await client.query("super_agent/memory_access", input_payload)


async def authorize_promotion(
    settings: Settings,
    *,
    agent_role: str | None,
    agent_risk_level: str | None,
    candidate_type: str,
    candidate_risk_level: str | None,
) -> AuthzDecision:
    client = OPAClient(settings)
    input_payload = {
        "agent": {
            "role": normalize_role(agent_role),
            "risk_level": normalize_risk(agent_risk_level),
        },
        "candidate": {
            "type": candidate_type,
            "risk_level": normalize_risk(candidate_risk_level),
        },
    }
    return await client.query("super_agent/promotion", input_payload)
