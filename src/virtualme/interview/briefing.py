from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from virtualme.storage.db import Dimension, Layer

INTERVIEW_PURPOSE = """INTERVIEW PURPOSE:
This is a long-running, multi-week VirtualMe interview. Its goal is to understand
the interviewee's behavior patterns, decision mechanisms, tradeoffs, boundaries,
and recurring ways of responding under pressure — not to judge, advise, diagnose,
or optimize them.
Treat confusion, hesitation, doubt, emotion, pain, contradiction, and reflection
about difficult topics as meaningful interview material — NOT as evasion. Genuine
evasion is only explicit refusal or deflection of the topic.
Ask one gentle question at a time. Prefer concrete episodes, choices, and
constraints. Do not advise, praise, diagnose, or over-interpret."""

MAX_RENDER_CHARS = 8000
MAX_ANCHORS = 12
MAX_TRIPLES = 12
MAX_COVERAGE_GAPS = 8
MAX_RECENT_TURNS = 8
MAX_ANCHOR_MODE_TURNS = 4


@dataclass(frozen=True)
class InterviewBriefing:
    purpose: str
    progress: str
    durable_summary: str
    coverage_gaps: str
    recent_transcript: str

    def render(self, mode: str) -> str:
        if mode == "classifier":
            sections = [
                self.purpose,
                _section("RECENT CONVERSATION", self.recent_transcript),
            ]
        elif mode == "anchor":
            sections = [
                self.purpose,
                _section(
                    "RECENT CONVERSATION",
                    _last_transcript_lines(self.recent_transcript, MAX_ANCHOR_MODE_TURNS),
                ),
            ]
        elif mode == "follow_up":
            sections = [
                self.purpose,
                _section("STILL TO COVER", self.coverage_gaps),
                _section("RECENT CONVERSATION", self.recent_transcript),
            ]
        else:
            sections = [
                self.purpose,
                _section("PROGRESS", self.progress),
                _section("WHAT WE KNOW SO FAR", self.durable_summary),
                _section("STILL TO COVER", self.coverage_gaps),
                _section("RECENT CONVERSATION", self.recent_transcript),
            ]
        return _fit_to_limit(sections, mode)


async def build_interview_briefing(
    db: Any, interviewee_id: str, session: Any, max_week: int
) -> InterviewBriefing:
    anchors_by_dimension = await db.load_anchors_summary(interviewee_id)
    triples = await db.load_triples(interviewee_id)
    coverage_gap = await db.compute_coverage_gap(interviewee_id)
    recent_turns = await db.load_recent_turns(session.id, MAX_RECENT_TURNS)

    return InterviewBriefing(
        purpose=INTERVIEW_PURPOSE,
        progress=f"Week {session.week} of {max_week}.",
        durable_summary=_format_durable_summary(anchors_by_dimension, triples),
        coverage_gaps=_format_coverage_gaps(coverage_gap),
        recent_transcript=_format_recent_transcript(recent_turns),
    )


def _section(title: str, content: str) -> str:
    return f"{title}:\n{content.strip() if content.strip() else 'None yet.'}"


def _format_durable_summary(
    anchors_by_dimension: dict[Dimension, list[Any]], triples: list[Any]
) -> str:
    lines: list[str] = []
    anchors = [
        anchor
        for dimension in Dimension
        for anchor in anchors_by_dimension.get(dimension, [])
        if str(getattr(anchor, "content", "")).strip()
    ]
    anchors.sort(
        key=lambda anchor: (
            0 if getattr(anchor, "triangulated", False) else 1,
            0 if getattr(anchor, "layer", None) == Layer.PRINCIPLE else 1,
        )
    )
    for anchor in anchors[:MAX_ANCHORS]:
        dimension = getattr(anchor, "dimension", "")
        dimension_text = getattr(dimension, "value", str(dimension))
        layer = getattr(anchor, "layer", "")
        layer_text = getattr(layer, "value", str(layer))
        marker = "triangulated " if getattr(anchor, "triangulated", False) else ""
        lines.append(f"- Anchor [{dimension_text}/{marker}{layer_text}]: {anchor.content}")

    prioritized_triples = [
        triple
        for triple in triples
        if str(getattr(triple, "object", "")).strip()
    ]
    relation_priority = {"red_line": 0, "value_anchor": 1, "skill": 2}
    prioritized_triples.sort(
        key=lambda triple: relation_priority.get(str(getattr(triple, "relation", "")), 3)
    )
    for triple in prioritized_triples[:MAX_TRIPLES]:
        lines.append(
            "- Triple "
            f"[{triple.relation}]: {triple.subject} -> {triple.object} "
            f"(confidence {float(getattr(triple, 'confidence', 0.0)):.2f})"
        )

    return "\n".join(lines) if lines else "No durable signal extracted yet."


def _format_coverage_gaps(coverage_gap: dict[Dimension, float]) -> str:
    if not coverage_gap:
        return "No computed coverage gaps yet."
    rows = sorted(
        coverage_gap.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    lines = []
    for dimension, gap in rows[:MAX_COVERAGE_GAPS]:
        dimension_text = getattr(dimension, "value", str(dimension))
        lines.append(f"- {dimension_text}: {float(gap):.2f}")
    return "\n".join(lines)


def _format_recent_transcript(turns: list[Any]) -> str:
    if not turns:
        return "No recent conversation yet."
    labels = {"user": "受訪者", "assistant": "訪談者"}
    lines = []
    for turn in turns[-MAX_RECENT_TURNS:]:
        role = labels.get(str(getattr(turn, "role", "")), str(getattr(turn, "role", "")))
        content = str(getattr(turn, "content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "No recent conversation yet."


def _last_transcript_lines(transcript: str, limit: int) -> str:
    lines = [line for line in transcript.splitlines() if line.strip()]
    if not lines:
        return "No recent conversation yet."
    return "\n".join(lines[-limit:])


def _fit_to_limit(sections: list[str], mode: str) -> str:
    text = "\n\n".join(sections)
    if len(text) <= MAX_RENDER_CHARS:
        return text

    if mode == "classifier":
        return _truncate_last_section(sections, MAX_RENDER_CHARS)
    if mode == "anchor":
        return _truncate_last_section(sections, MAX_RENDER_CHARS)

    trimmed = sections[:]
    if trimmed:
        trimmed[-1] = _truncate_section(trimmed[-1], MAX_RENDER_CHARS // 4)
    text = "\n\n".join(trimmed)
    if len(text) <= MAX_RENDER_CHARS:
        return text

    if len(trimmed) >= 3:
        trimmed[2] = _truncate_section(trimmed[2], MAX_RENDER_CHARS // 4)
    return _truncate_last_section(trimmed, MAX_RENDER_CHARS)


def _truncate_last_section(sections: list[str], limit: int) -> str:
    text = "\n\n".join(sections)
    if len(text) <= limit:
        return text
    if not sections:
        return ""
    prefix = "\n\n".join(sections[:-1])
    separator = "\n\n" if prefix else ""
    available = max(0, limit - len(prefix) - len(separator) - len("\n[truncated]"))
    sections[-1] = sections[-1][:available].rstrip() + "\n[truncated]"
    return "\n\n".join(sections)


def _truncate_section(section: str, target: int) -> str:
    if len(section) <= target:
        return section
    return section[: max(0, target - len("\n[truncated]"))].rstrip() + "\n[truncated]"
