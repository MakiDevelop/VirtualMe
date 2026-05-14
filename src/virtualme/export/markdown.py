from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from virtualme.interview.pii import scrub_pii
from virtualme.storage.db import DB, Anchor, Dimension


async def export_markdown(db: DB, interviewee_id: str, out_dir: Path) -> list[Path]:
    """Export current local anchors into a small markdown archive."""
    anchors = await db.load_anchors_summary(interviewee_id)
    target = out_dir / interviewee_id
    target.mkdir(parents=True, exist_ok=True)

    files = {
        "index.md": _render_index(interviewee_id, anchors),
        "anchors.md": _render_anchors(anchors),
        "principles.md": _render_principles(anchors),
    }
    written: list[Path] = []
    for name, content in files.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def _render_index(interviewee_id: str, anchors: dict[Dimension, list[Anchor]]) -> str:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    total = sum(len(items) for items in anchors.values())
    triangulated = sum(1 for items in anchors.values() for anchor in items if anchor.triangulated)
    lines = [
        f"# VirtualMe Export: {interviewee_id}",
        "",
        f"- Generated at: {generated_at}",
        f"- Total anchors: {total}",
        f"- Triangulated principles: {triangulated}",
        "",
        "## Counts by Dimension",
        "",
    ]
    for dimension in Dimension:
        items = anchors.get(dimension, [])
        confirmed = sum(1 for anchor in items if anchor.triangulated)
        lines.append(f"- {dimension.value}: {len(items)} anchors, {confirmed} triangulated")
    return "\n".join(lines) + "\n"


def _render_anchors(anchors: dict[Dimension, list[Anchor]]) -> str:
    lines = ["# Anchors", ""]
    for dimension in Dimension:
        lines.extend([f"## {dimension.value}", ""])
        items = anchors.get(dimension, [])
        if not items:
            lines.extend(["_(no anchors yet)_", ""])
            continue
        for anchor in items:
            lines.append(_anchor_bullet(anchor))
        lines.append("")
    return "\n".join(lines)


def _render_principles(anchors: dict[Dimension, list[Anchor]]) -> str:
    lines = ["# Triangulated Principles", ""]
    for dimension in Dimension:
        items = [
            anchor
            for anchor in anchors.get(dimension, [])
            if anchor.triangulated
        ]
        lines.extend([f"## {dimension.value}", ""])
        if not items:
            lines.extend(["_(no triangulated principles yet)_", ""])
            continue
        for anchor in items:
            lines.append(_anchor_bullet(anchor))
        lines.append("")
    return "\n".join(lines)


def _anchor_bullet(anchor: Anchor) -> str:
    content = scrub_pii(anchor.content).scrubbed_text
    question_ids = ", ".join(anchor.source_question_ids) or "unknown"
    turn_ids = ", ".join(str(turn_id) for turn_id in anchor.source_turn_ids) or "unknown"
    status = "triangulated" if anchor.triangulated else "emerging"
    return f"- [{anchor.layer.value}; {status}; questions: {question_ids}; turns: {turn_ids}] {content}"

