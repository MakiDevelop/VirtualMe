from __future__ import annotations

import hashlib
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from virtualme.interview.pii import scrub_pii
from virtualme.snapshot.promotion_gate import PromotionDecision, PromotionTier, classify_anchor
from virtualme.storage.db import DB, Anchor, Dimension

SCHEMA_VERSION = "0.5"

DIMENSION_DESCRIPTIONS = {
    Dimension.SOUL: "Identity, values, and durable red lines.",
    Dimension.VOICE: "Voice patterns and reusable expression samples.",
    Dimension.SKILL: "Domain know-how, practices, and task preferences.",
    Dimension.PEOPLE: "Relationship context and recurring people schemas.",
    Dimension.HISTORY: "Life events and durable personal timeline context.",
    Dimension.JOURNAL: "Reflections, interpretations, and periodic event notes.",
    Dimension.BOUNDARIES: "Refusals, privacy rules, and persona update protocol.",
    Dimension.STATE: "Current-state snapshot that may become stale over time.",
}


async def export_markdown(db: DB, interviewee_id: str, out_dir: Path) -> list[Path]:
    """Export current local anchors into the persona markdown archive."""
    anchors = await db.load_anchors_summary(interviewee_id)
    source_session_counts = await db.load_anchor_source_session_counts(interviewee_id)
    promotion_decisions = {
        _anchor_key(anchor): classify_anchor(
            anchor,
            source_session_count=source_session_counts.get(anchor.id or -1, 0),
        )
        for items in anchors.values()
        for anchor in items
    }
    target = out_dir / interviewee_id
    target.mkdir(parents=True, exist_ok=True)
    exported_at = datetime.now(UTC).isoformat(timespec="seconds")
    export_id = str(uuid4())

    files: dict[str, str] = {
        "START_HERE.md": _render_start_here(interviewee_id, anchors, exported_at),
        "index.md": _render_index(interviewee_id, anchors, exported_at),
        **{
            f"{dimension.value}.md": _render_dimension_file(
                dimension,
                anchors.get(dimension, []),
                exported_at,
                promotion_decisions,
            )
            for dimension in Dimension
        },
    }
    files["manifest.json"] = _render_manifest(
        interviewee_id=interviewee_id,
        exported_at=exported_at,
        export_id=export_id,
        anchors=anchors,
        files=files,
    )

    written: list[Path] = []
    for name, content in files.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def _render_start_here(
    interviewee_id: str,
    anchors: dict[Dimension, list[Anchor]],
    exported_at: str,
) -> str:
    total = sum(len(items) for items in anchors.values())
    triangulated = sum(1 for items in anchors.values() for anchor in items if anchor.triangulated)
    lines = [
        f"# Start Here: {interviewee_id}",
        "",
        "This folder is your VirtualMe persona archive: human-editable Markdown files",
        "extracted from the interview process, with a machine-readable manifest beside them.",
        "",
        f"- Exported at: {exported_at}",
        f"- Persona files: {len(Dimension)}",
        f"- Total anchors: {total}",
        f"- Legacy triangulated anchors: {triangulated}",
        "",
        "## Recommended Reading Order",
        "",
        "1. [SOUL.md](SOUL.md) - core identity and values.",
        "2. [VOICE.md](VOICE.md) - how the agent should sound.",
        "3. [BOUNDARIES.md](BOUNDARIES.md) - what the agent should not do.",
        "4. [index.md](index.md) - complete file list and counts.",
        "",
        "## Archive Files",
        "",
    ]
    for dimension in Dimension:
        lines.append(f"- [{dimension.value}.md]({dimension.value}.md): {DIMENSION_DESCRIPTIONS[dimension]}")
    lines.extend(
        [
            "",
            "## Machine-Readable Metadata",
            "",
            "- [manifest.json](manifest.json) contains schema version, counts, and payload file hashes.",
            "- Markdown frontmatter contains per-file dimension metadata.",
            "- Provenance details are folded under each item so the main text stays readable.",
            "- PII scrubbing applies to exported anchor content; archive IDs and folder names are unchanged.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_index(
    interviewee_id: str,
    anchors: dict[Dimension, list[Anchor]],
    exported_at: str,
) -> str:
    total = sum(len(items) for items in anchors.values())
    triangulated = sum(1 for items in anchors.values() for anchor in items if anchor.triangulated)
    lines = [
        f"# VirtualMe Export: {interviewee_id}",
        "",
        f"- Generated at: {exported_at}",
        f"- Total anchors: {total}",
        f"- Legacy triangulated principles: {triangulated}",
        f"- Schema version: {SCHEMA_VERSION}",
        "",
        "## Persona Files",
        "",
    ]
    for dimension in Dimension:
        items = anchors.get(dimension, [])
        confirmed = sum(1 for anchor in items if anchor.triangulated)
        lines.append(
            f"- [{dimension.value}.md]({dimension.value}.md): "
            f"{len(items)} anchors, {confirmed} triangulated"
        )
    return "\n".join(lines) + "\n"


def _render_dimension_file(
    dimension: Dimension,
    anchors: list[Anchor],
    exported_at: str,
    promotion_decisions: dict[int, PromotionDecision] | None = None,
) -> str:
    decisions = promotion_decisions or {
        _anchor_key(anchor): classify_anchor(anchor) for anchor in anchors
    }
    stable = [
        anchor
        for anchor in anchors
        if decisions[_anchor_key(anchor)].tier
        in {PromotionTier.CROSS_SESSION, PromotionTier.VALIDATED}
    ]
    recurring = [
        anchor
        for anchor in anchors
        if decisions[_anchor_key(anchor)].tier == PromotionTier.RECURRING
    ]
    emerging = [
        anchor
        for anchor in anchors
        if decisions[_anchor_key(anchor)].tier == PromotionTier.OBSERVED
    ]
    lines = [
        "---",
        f'schema_version: "{SCHEMA_VERSION}"',
        f"dimension: {dimension.value}",
        f"exported_at: {exported_at}",
        f"anchor_count: {len(anchors)}",
        f"validated_or_cross_session_count: {len(stable)}",
        f"recurring_unvalidated_count: {len(recurring)}",
        f"emerging_count: {len(emerging)}",
        "anchor_content_pii_scrubbed: true",
        "---",
        "",
        f"# {dimension.value}",
        "",
        DIMENSION_DESCRIPTIONS[dimension],
        "",
    ]

    lines.extend(
        [
            "## Validated Patterns",
            "",
            "_Only cross-session validated patterns appear here._",
            "",
        ]
    )
    if not stable:
        lines.extend(["_(no validated patterns yet)_", ""])
    else:
        for anchor in stable:
            lines.extend(_anchor_block(anchor, decisions[_anchor_key(anchor)]))
        lines.append("")

    lines.extend(["## Recurring but Unvalidated Patterns", ""])
    if not recurring:
        lines.extend(["_(no recurring unvalidated patterns yet)_", ""])
    else:
        lines.append("_These need cross-session validation before they can be treated as stable._")
        lines.append("")
        for anchor in recurring:
            lines.extend(_anchor_block(anchor, decisions[_anchor_key(anchor)]))
        lines.append("")

    lines.extend(["## Emerging Patterns", ""])
    if not emerging:
        lines.extend(["_(no emerging patterns yet)_", ""])
    else:
        for anchor in emerging:
            lines.extend(_anchor_block(anchor, decisions[_anchor_key(anchor)]))
        lines.append("")

    return "\n".join(lines)


def _anchor_block(anchor: Anchor, decision: PromotionDecision | None = None) -> list[str]:
    content = scrub_pii(anchor.content).scrubbed_text
    question_ids = ", ".join(anchor.source_question_ids) or "unknown"
    turn_ids = ", ".join(str(turn_id) for turn_id in anchor.source_turn_ids) or "unknown"
    decision = decision or classify_anchor(anchor)
    return [
        "-",
        "",
        *_blockquote_lines(content),
        "",
        "  <details>",
        "  <summary>Provenance</summary>",
        "",
        f"  - Layer: {anchor.layer.value}",
        f"  - Legacy triangulated: {'yes' if anchor.triangulated else 'no'}",
        f"  - Promotion tier: {decision.tier.value}",
        f"  - Promotion reason: {decision.reason}",
        f"  - Missing evidence: {', '.join(decision.missing_evidence) or 'none'}",
        f"  - Questions: {question_ids}",
        f"  - Turns: {turn_ids}",
        "",
        "  </details>",
        "",
    ]


def _anchor_key(anchor: Anchor) -> int:
    return anchor.id if anchor.id is not None else id(anchor)


def _blockquote_lines(content: str) -> list[str]:
    escaped = html.escape(content, quote=False)
    return [f"  > {line}" if line else "  >" for line in escaped.splitlines()]


def _render_manifest(
    interviewee_id: str,
    exported_at: str,
    export_id: str,
    anchors: dict[Dimension, list[Anchor]],
    files: dict[str, str],
) -> str:
    dimensions = {}
    for dimension in Dimension:
        items = anchors.get(dimension, [])
        dimensions[dimension.value] = {
            "file": f"{dimension.value}.md",
            "description": DIMENSION_DESCRIPTIONS[dimension],
            "anchor_count": len(items),
            "triangulated_count": sum(1 for anchor in items if anchor.triangulated),
            "emerging_count": sum(1 for anchor in items if not anchor.triangulated),
        }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "export_id": export_id,
        "interviewee_id": interviewee_id,
        "exported_at": exported_at,
        "persona_files": [f"{dimension.value}.md" for dimension in Dimension],
        "archive_files": sorted([*files, "manifest.json"]),
        "human_entrypoint": "START_HERE.md",
        "technical_index": "index.md",
        "pii_scrub_scope": "anchor_content",
        "dimensions": dimensions,
        "payload_files": {
            name: {
                "sha256": f"sha256:{_sha256(content)}",
                "bytes": len(content.encode("utf-8")),
            }
            for name, content in sorted(files.items())
        },
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
