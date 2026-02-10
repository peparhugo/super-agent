#!/usr/bin/env python3
"""Orchestrate planner/developer/tester agents with MCP tooling."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openai_agents import Agent, Runner, set_tracing
from openai_agents.mcp import MCPServer

LOG_DIR = Path("logs/orchestration")


@dataclass
class RoleConfig:
    name: str
    instructions: str


ROLE_CONFIGS = {
    "planner": RoleConfig(
        name="Planner",
        instructions=(
            "You are the planning agent. Produce a step-by-step execution plan with risk notes "
            "and verification steps."
        ),
    ),
    "developer": RoleConfig(
        name="Developer",
        instructions=(
            "You are the developer agent. Implement the plan, summarize changes, and note blockers."
        ),
    ),
    "tester": RoleConfig(
        name="Tester",
        instructions=(
            "You are the tester agent. Validate changes, list tests run, and report gaps."
        ),
    ),
}


@dataclass
class TraceContext:
    thread_id: str
    log_path: Path


def setup_trace(thread_id: str) -> TraceContext:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"trace-{thread_id}.jsonl"
    set_tracing(str(log_path))
    return TraceContext(thread_id=thread_id, log_path=log_path)


def emit_trace(trace: TraceContext, payload: dict[str, Any]) -> None:
    payload_with_meta = {
        "thread_id": trace.thread_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    with trace.log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload_with_meta) + "\n")


def build_agents(tools: Iterable[Any]) -> dict[str, Agent]:
    return {
        key: Agent(name=config.name, instructions=config.instructions, tools=list(tools))
        for key, config in ROLE_CONFIGS.items()
    }


def run_role(agent: Agent, role: str, input_text: str, trace: TraceContext) -> str:
    emit_trace(trace, {"event": "role_start", "role": role, "input": input_text})
    result = Runner.run(agent, input=input_text)
    output_text = getattr(result, "output_text", str(result))
    emit_trace(trace, {"event": "role_end", "role": role, "output": output_text})
    return output_text


def start_mcp_server() -> MCPServer:
    return MCPServer(
        name="codex",
        command=["codex", "mcp-server"],
        env=os.environ.copy(),
    )


def orchestrate(role: str, input_text: str) -> None:
    thread_id = str(uuid.uuid4())
    trace = setup_trace(thread_id)
    emit_trace(trace, {"event": "thread_start", "role": role})

    mcp_server = start_mcp_server()
    with mcp_server:
        tools = mcp_server.tools()
        agents = build_agents(tools)

        if role == "full":
            plan = run_role(agents["planner"], "planner", input_text, trace)
            dev_input = f"Plan:\n{plan}\n\nImplement the plan."
            build = run_role(agents["developer"], "developer", dev_input, trace)
            test_input = f"Implementation summary:\n{build}\n\nVerify the work."
            run_role(agents["tester"], "tester", test_input, trace)
        else:
            run_role(agents[role], role, input_text, trace)

    emit_trace(trace, {"event": "thread_end", "role": role})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orchestrate Agents SDK roles with MCP tools.")
    parser.add_argument(
        "--role",
        default="full",
        choices=["planner", "developer", "tester", "full"],
        help="Role to execute (default: full sequence).",
    )
    parser.add_argument("--input", required=True, help="Prompt to send to the agent workflow.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    orchestrate(args.role, args.input)


if __name__ == "__main__":
    main()
