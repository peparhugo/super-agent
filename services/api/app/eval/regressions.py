from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    description: str
    expected_keywords: tuple[str, ...]


SKILL_REGRESSIONS: tuple[RegressionCase, ...] = (
    RegressionCase(
        case_id="skill-basic-safety",
        description="Ensure skill includes guardrails and safe defaults.",
        expected_keywords=("safety", "guardrail", "fallback"),
    ),
    RegressionCase(
        case_id="skill-observability",
        description="Ensure skill description mentions telemetry or monitoring.",
        expected_keywords=("monitor", "log", "trace"),
    ),
)

AGENT_REGRESSIONS: tuple[RegressionCase, ...] = (
    RegressionCase(
        case_id="agent-routing",
        description="Agent should describe routing or delegation behavior.",
        expected_keywords=("route", "delegate", "triage"),
    ),
    RegressionCase(
        case_id="agent-memory",
        description="Agent config should mention memory or retrieval.",
        expected_keywords=("memory", "retrieve", "embedding"),
    ),
)


def get_regression_suite(candidate_type: str) -> tuple[RegressionCase, ...]:
    if candidate_type == "skill":
        return SKILL_REGRESSIONS
    if candidate_type == "agent":
        return AGENT_REGRESSIONS
    return ()
