from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from virtualme.interview.depth_evaluator import evaluate_depth
from virtualme.interview.follow_up import FollowUpRule, select_rule
from virtualme.storage.db import Layer


@dataclass
class CaseResult:
    id: str
    depth_expected: str
    depth_actual: str | None
    depth_ok: bool | None
    rule_expected: str | None
    rule_actual: str | None
    rule_ok: bool


@dataclass
class EvalReport:
    results: list[CaseResult]
    rule_accuracy: float
    depth_accuracy: float | None
    with_llm: bool
    generated_at: str


def load_fixtures(path: str | Path | None = None) -> list[dict[str, Any]]:
    if path is None:
        text = resources.files("virtualme.evals").joinpath("fixtures.yaml").read_text(
            encoding="utf-8"
        )
    else:
        text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    cases = data.get("cases", []) if isinstance(data, dict) else []
    if not isinstance(cases, list):
        raise ValueError("fixtures must contain a cases list")
    return cases


async def run_eval(cases: list[dict[str, Any]], claude=None) -> EvalReport:
    results: list[CaseResult] = []
    with_llm = claude is not None

    for case in cases:
        depth_expected = str(case["expected_depth"])
        rule_expected = _optional_str(case.get("expected_rule"))

        depth = Layer(depth_expected)
        rule = select_rule(case["answer"], depth, accumulated_anchors=[])
        rule_actual = _rule_value(rule)
        rule_ok = rule_actual == rule_expected

        depth_actual = None
        depth_ok = None
        if with_llm:
            actual_layer = await evaluate_depth(case["answer"], case["question"], claude)
            depth_actual = actual_layer.value
            depth_ok = depth_actual == depth_expected

        results.append(
            CaseResult(
                id=str(case["id"]),
                depth_expected=depth_expected,
                depth_actual=depth_actual,
                depth_ok=depth_ok,
                rule_expected=rule_expected,
                rule_actual=rule_actual,
                rule_ok=rule_ok,
            )
        )

    total = len(results)
    rule_accuracy = sum(result.rule_ok for result in results) / total if total else 0.0
    depth_accuracy = None
    if with_llm:
        depth_accuracy = (
            sum(result.depth_ok is True for result in results) / total if total else 0.0
        )

    return EvalReport(
        results=results,
        rule_accuracy=rule_accuracy,
        depth_accuracy=depth_accuracy,
        with_llm=with_llm,
        generated_at=datetime.now(UTC).isoformat(),
    )


def render_scorecard(report: EvalReport) -> str:
    lines = [
        "# Engine Evaluation Scorecard",
        "",
        f"Generated at: {report.generated_at}",
        "",
        "## Summary",
        "",
        f"- Total cases: {len(report.results)}",
        f"- Rule accuracy: {_percent(report.rule_accuracy)}",
    ]
    if report.with_llm and report.depth_accuracy is not None:
        lines.append(f"- Depth accuracy: {_percent(report.depth_accuracy)}")
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| ID | Depth Expected | Depth Actual | Rule Expected | Rule Actual | Pass |",
            "|---|---|---|---|---|---|",
        ]
    )

    for result in report.results:
        passed = result.rule_ok and (result.depth_ok is not False)
        lines.append(
            "| "
            f"{result.id} | "
            f"{result.depth_expected} | "
            f"{_display(result.depth_actual)} | "
            f"{_display(result.rule_expected)} | "
            f"{_display(result.rule_actual)} | "
            f"{'yes' if passed else 'no'} |"
        )

    failed = [
        result.id
        for result in report.results
        if not result.rule_ok or result.depth_ok is False
    ]
    lines.extend(
        [
            "",
            "## Failed Cases",
            "",
            ", ".join(failed) if failed else "None",
            "",
        ]
    )
    return "\n".join(lines)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _rule_value(rule: FollowUpRule | None) -> str | None:
    return None if rule is None else rule.value


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _display(value: str | None) -> str:
    return "" if value is None else value
