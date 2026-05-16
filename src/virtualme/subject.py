"""Subject profile rendering - the human-readable SUBJECT.md artifact."""

from __future__ import annotations

from pydantic import BaseModel

from virtualme.storage.db import Anchor, ChecklistItem, Dimension, Subject

# HR PoC: VOICE / BOUNDARIES are extraction priorities.
DIMENSION_WEIGHTS: dict[Dimension, int] = {
    Dimension.VOICE: 3,
    Dimension.BOUNDARIES: 3,
    Dimension.SOUL: 2,
    Dimension.SKILL: 2,
    Dimension.PEOPLE: 2,
    Dimension.HISTORY: 1,
    Dimension.JOURNAL: 1,
    Dimension.STATE: 1,
}
TARGET_ANCHORS_PER_DIMENSION = 3


class DimensionScore(BaseModel):
    dimension: Dimension
    anchor_count: int
    triangulated_count: int
    coverage: float


class CompletenessReport(BaseModel):
    per_dimension: list[DimensionScore]
    total_score: float
    weakest: Dimension | None


def render_subject_md(subject: Subject) -> str:
    """Render a subject profile as a human-readable Markdown card."""
    title = subject.display_name or subject.interviewee_id
    lines = [
        f"# Subject: {title}",
        "",
        f"- Interviewee ID: {subject.interviewee_id}",
        f"- Display name: {subject.display_name or ''}",
        f"- Domain: {subject.domain.value}",
        f"- Goal: {subject.goal or ''}",
        f"- Status: {subject.status.value}",
        f"- Created at: {subject.created_at or ''}",
        f"- Updated at: {subject.updated_at or ''}",
        "",
    ]
    return "\n".join(lines)


def render_checklist_md(items: list[ChecklistItem]) -> str:
    lines = []
    for item in items:
        checkbox = "x" if item.done else " "
        line = f"- [{checkbox}] {item.label}"
        if item.note:
            line = f"{line} - {item.note}"
        lines.append(line)
    return "\n".join(lines)


def score_completeness(
    anchors_by_dimension: dict[Dimension, list[Anchor]],
) -> CompletenessReport:
    """Graded extraction-completeness score for observing a subject's run.

    Per-dimension coverage is based on anchors collected against the target,
    with a small bonus for at least one triangulated anchor. Total is the
    weighted average across configured dimensions on a 0-100 scale.
    """
    per_dimension: list[DimensionScore] = []

    for dimension in DIMENSION_WEIGHTS:
        anchors = anchors_by_dimension.get(dimension, [])
        anchor_count = len(anchors)
        triangulated_count = sum(1 for anchor in anchors if anchor.triangulated)
        coverage = min(1.0, anchor_count / TARGET_ANCHORS_PER_DIMENSION)
        if triangulated_count > 0:
            coverage = min(1.0, coverage + 0.15)
        per_dimension.append(
            DimensionScore(
                dimension=dimension,
                anchor_count=anchor_count,
                triangulated_count=triangulated_count,
                coverage=coverage,
            )
        )

    total_weight = sum(DIMENSION_WEIGHTS.values())
    total = sum(
        score.coverage * DIMENSION_WEIGHTS[score.dimension] for score in per_dimension
    )
    weakest = min(per_dimension, key=lambda score: score.coverage).dimension

    return CompletenessReport(
        per_dimension=per_dimension,
        total_score=round((total / total_weight) * 100, 1),
        weakest=weakest,
    )
