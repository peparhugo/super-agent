from __future__ import annotations

from dataclasses import dataclass

from app.eval.regressions import RegressionCase, get_regression_suite


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    score: float
    details: dict


def _to_text(payload: dict) -> str:
    parts = [payload.get("description"), payload.get("summary")]
    parts.append(" ".join(str(item) for item in payload.get("tags", []) if item))
    return " ".join(part for part in parts if part).lower()


def run_unit_checks(candidate_type: str, payload: dict) -> list[CheckResult]:
    name = payload.get("name")
    description = payload.get("description")
    spec = payload.get("spec") or payload.get("config") or {}
    checks = [
        CheckResult(
            name="has-name",
            passed=bool(name),
            score=1.0 if name else 0.0,
            details={"name": name},
        ),
        CheckResult(
            name="has-description",
            passed=bool(description),
            score=1.0 if description else 0.0,
            details={"length": len(description or "")},
        ),
        CheckResult(
            name="has-domain",
            passed=bool(spec.get("domain")),
            score=1.0 if spec.get("domain") else 0.0,
            details={"domain": spec.get("domain")},
        ),
    ]
    if candidate_type == "agent":
        checks.append(
            CheckResult(
                name="agent-has-template",
                passed=bool(spec.get("template") or spec.get("prompt")),
                score=1.0 if spec.get("template") or spec.get("prompt") else 0.0,
                details={"template_present": bool(spec.get("template") or spec.get("prompt"))},
            )
        )
    return checks


def run_regression_checks(candidate_type: str, payload: dict) -> list[CheckResult]:
    text = _to_text(payload)
    results: list[CheckResult] = []
    for case in get_regression_suite(candidate_type):
        hits = [keyword for keyword in case.expected_keywords if keyword in text]
        passed = len(hits) > 0
        results.append(
            CheckResult(
                name=f"regression:{case.case_id}",
                passed=passed,
                score=1.0 if passed else 0.0,
                details={
                    "description": case.description,
                    "expected_keywords": case.expected_keywords,
                    "matched_keywords": hits,
                },
            )
        )
    return results


def run_adversarial_checks(candidate_type: str, payload: dict) -> list[CheckResult]:
    text = _to_text(payload)
    forbidden = ("unsafe", "hack", "exploit")
    hits = [keyword for keyword in forbidden if keyword in text]
    return [
        CheckResult(
            name="adversarial:forbidden-terms",
            passed=len(hits) == 0,
            score=1.0 if len(hits) == 0 else 0.0,
            details={"forbidden_terms": forbidden, "matched_terms": hits},
        )
    ]


def run_model_graded_checks(candidate_type: str, payload: dict) -> list[CheckResult]:
    description = payload.get("description") or ""
    length_score = min(len(description) / 200.0, 1.0)
    score = round(0.6 * length_score + 0.4, 2)
    passed = score >= 0.7
    return [
        CheckResult(
            name="model-graded:description-quality",
            passed=passed,
            score=score,
            details={"description_length": len(description)},
        )
    ]


def summarize_results(results: list[CheckResult]) -> dict:
    passed = all(result.passed for result in results)
    avg_score = round(sum(result.score for result in results) / max(len(results), 1), 3)
    return {"passed": passed, "average_score": avg_score}


def run_all_checks(candidate_type: str, payload: dict) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.extend(run_unit_checks(candidate_type, payload))
    results.extend(run_regression_checks(candidate_type, payload))
    results.extend(run_adversarial_checks(candidate_type, payload))
    results.extend(run_model_graded_checks(candidate_type, payload))
    return results
