from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from virtualme.config import Settings, sqlite_path
from virtualme.interview.pii import scrub_pii
from virtualme.storage.db import DB, Anchor, Dimension


async def export_blind_test_prepare(
    db: DB,
    interviewee_id: str,
    week: int,
    out_dir: Path,
) -> list[Path]:
    if week < 1 or week > 8:
        raise ValueError("--week must be between 1 and 8")

    anchors = await db.load_anchors_summary(interviewee_id)
    target = out_dir / interviewee_id / f"week-{week}"
    target.mkdir(parents=True, exist_ok=True)

    scenario_count = 8 if week >= 8 else 5
    files = {
        "instructions.md": _render_instructions(interviewee_id, week, scenario_count),
        "scorecard.md": _render_scorecard(week, scenario_count),
        "persona-context.md": _render_persona_context(interviewee_id, week, anchors),
    }
    written: list[Path] = []
    for name, content in files.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def _render_instructions(interviewee_id: str, week: int, scenario_count: int) -> str:
    return "\n".join(
        [
            f"# Blind-Test Instructions: {interviewee_id} Week {week}",
            "",
            "## Operator Steps",
            "",
            f"1. Prepare {scenario_count} realistic scenarios the interviewee has not seen.",
            "2. Ask the interviewee to write one response per scenario.",
            "3. Ask the agent to write one response per same scenario.",
            "4. Shuffle each human/agent pair into Alpha/Beta without revealing the source.",
            "5. Ask the evaluator to pick which response was written by the interviewee.",
            "6. Fill `scorecard.md`, then record results with `python -m virtualme.blind_test`.",
            "",
            "This bundle does not generate scenarios, shuffle responses, or assemble VOICE",
            "retrieval. Until persona summarization ships, assemble the agent context manually.",
            "",
            "## Verdict Bands",
            "",
            "- `< 50%`: overfit-warning",
            "- `50-60%`: ship-ready",
            "- `> 60%`: needs-work",
            "",
            "The score is not a judgment of the human. It only measures whether the agent is",
            "currently distinguishable in this blind-test setup.",
            "",
        ]
    )


def _render_scorecard(week: int, scenario_count: int) -> str:
    lines = [
        f"# Blind-Test Scorecard: Week {week}",
        "",
        "| ID | Shuffled # | Guess (mine/agent) | Correct? (0/1) | Notes |",
        "|---|---|---|---|---|",
    ]
    for index in range(1, scenario_count + 1):
        lines.append(f"| T{index} |  |  |  |  |")
    lines.extend(
        [
            "",
            f"Accuracy: ___ / {scenario_count} = ___%",
            "Verdict: ___",
            "",
            "After scoring, convert `Correct?` to keyed results, for example:",
            "",
            "```bash",
            "python -m virtualme.blind_test --week 5 --results T1=1,T2=0,T3=1,T4=0,T5=1",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _render_persona_context(
    interviewee_id: str,
    week: int,
    anchors: dict[Dimension, list[Anchor]],
) -> str:
    lines = [
        f"# Persona Context: {interviewee_id} Week {week}",
        "",
        "Stopgap operator context from legacy recurring principles only. These are not",
        "validated traits. Do not show this context to the evaluator during scoring.",
        "",
        "## Counts by Dimension",
        "",
    ]
    for dimension in Dimension:
        items = anchors.get(dimension, [])
        recurring = sum(1 for anchor in items if anchor.triangulated)
        lines.append(
            f"- {dimension.value}: {len(items)} anchors, "
            f"{recurring} legacy recurring/unvalidated"
        )
    lines.extend(["", "## Legacy Recurring Principles", ""])
    for dimension in Dimension:
        lines.extend([f"## {dimension.value}", ""])
        items = [anchor for anchor in anchors.get(dimension, []) if anchor.triangulated]
        if not items:
            lines.extend(["_(no anchors yet)_", ""])
            continue
        for anchor in sorted(items, key=lambda item: (not item.triangulated, item.layer.value)):
            lines.append(_anchor_line(anchor))
        lines.append("")
    return "\n".join(lines)


def _anchor_line(anchor: Anchor) -> str:
    status = "legacy recurring/unvalidated" if anchor.triangulated else "emerging"
    content = scrub_pii(anchor.content).scrubbed_text
    return f"- [{anchor.layer.value}; {status}] {content}"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare manual VirtualMe blind-test materials.")
    parser.add_argument("--interviewee", default="local")
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--out", type=Path, default=Path("./exports/blind-test"))
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    database_url = args.db if args.db is not None else Settings().database_url
    db = DB(sqlite_path(database_url))
    await db.init()
    paths = await export_blind_test_prepare(db, args.interviewee, args.week, args.out)
    for path in paths:
        print(path)


if __name__ == "__main__":
    asyncio.run(main())
