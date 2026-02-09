from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.memory.retrieval import MemoryPointer
from app.runtime.prompt_compiler import PromptInputs, compile_prompt
from app.settings import Settings


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    description: str
    tool: str | None
    depends_on: list[str]


@dataclass(frozen=True)
class PlanResult:
    steps: list[PlanStep]
    notes: str | None = None


class PlannerClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def create_plan(
        self,
        *,
        user_input: str,
        agent_template: dict,
        skill_pointers: list[MemoryPointer],
        memory_pointers: list[MemoryPointer],
    ) -> PlanResult:
        system_preamble = (
            "You are a planning engine. Create a concise step-by-step plan."
            "Return valid JSON with keys: steps (list) and notes (string)."
            "Each step must include: step_id, description, tool, depends_on."
        )
        prompt = compile_prompt(
            PromptInputs(
                system_preamble=system_preamble,
                agent_template=agent_template,
                user_input=user_input,
                skill_pointers=skill_pointers,
                memory_pointers=memory_pointers,
            )
        )
        payload = {
            "model": self._settings.planner_model,
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.planner_max_tokens,
            "messages": [
                {"role": "system", "content": system_preamble},
                {"role": "user", "content": prompt},
            ],
        }
        if self._settings.llm_api_key:
            headers = {"Authorization": f"Bearer {self._settings.llm_api_key}"}
        else:
            headers = {}
        async with httpx.AsyncClient(base_url=self._settings.llm_base_url, timeout=60) as client:
            response = await client.post("/v1/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = _extract_message_content(data)
        raw = _extract_json(content)
        steps = [
            PlanStep(
                step_id=str(step.get("step_id", idx + 1)),
                description=str(step.get("description", "")).strip(),
                tool=step.get("tool"),
                depends_on=[str(dep) for dep in step.get("depends_on", [])],
            )
            for idx, step in enumerate(raw.get("steps", []))
        ]
        notes = raw.get("notes")
        return PlanResult(steps=steps, notes=notes)


def _extract_message_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""


def _extract_json(content: str) -> dict[str, Any]:
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return {}
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return {}
