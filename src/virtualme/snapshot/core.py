from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from virtualme.interview.pii import scrub_pii
from virtualme.interview.triples import PersonaTriple
from virtualme.storage.db import DB, Anchor, Dimension, Layer

SNAPSHOT_SCHEMA_VERSION = "0.1"

CORE_DIMENSIONS = (
    Dimension.SOUL,
    Dimension.BOUNDARIES,
    Dimension.VOICE,
    Dimension.SKILL,
    Dimension.PEOPLE,
)

DECISION_KEYWORDS = (
    "choose",
    "choice",
    "decide",
    "decision",
    "tradeoff",
    "constraint",
    "refuse",
    "boundary",
    "選",
    "選擇",
    "決定",
    "取捨",
    "權衡",
    "限制",
    "拒絕",
    "界線",
    "底線",
    "預算",
    "範圍",
    "時程",
)


class EvidenceItem(BaseModel):
    kind: str
    dimension: Dimension | None = None
    layer: Layer | None = None
    content: str
    source_turn_ids: list[int] = Field(default_factory=list)
    source_question_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None


class SoulLiteHypothesis(BaseModel):
    id: str
    dimension: Dimension
    hypothesis: str
    confidence: str
    evidence: list[EvidenceItem]
    missing_evidence: str
    suggested_follow_up: str
    needs_verification: bool


class MiniBlindTestItem(BaseModel):
    id: str
    dimension: Dimension
    scenario: str
    what_to_compare: str
    evidence_hint: str


class SnapshotBundle(BaseModel):
    schema_version: str = SNAPSHOT_SCHEMA_VERSION
    interviewee_id: str
    generated_at: str
    hypotheses: list[SoulLiteHypothesis]
    mini_blind_test: list[MiniBlindTestItem]
    feedback_routes: list[str]


@dataclass(frozen=True)
class _Candidate:
    dimension: Dimension
    content: str
    evidence: EvidenceItem
    weight: int


async def build_snapshot_bundle(db: DB, interviewee_id: str) -> SnapshotBundle:
    anchors = await db.load_anchors_summary(interviewee_id)
    triples = await db.load_triples(interviewee_id)
    return build_snapshot_bundle_from_data(
        interviewee_id=interviewee_id,
        anchors=anchors,
        triples=triples,
    )


def build_snapshot_bundle_from_data(
    *,
    interviewee_id: str,
    anchors: dict[Dimension, list[Anchor]],
    triples: list[PersonaTriple],
) -> SnapshotBundle:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    hypotheses = _build_hypotheses(anchors, triples)
    return SnapshotBundle(
        interviewee_id=interviewee_id,
        generated_at=generated_at,
        hypotheses=hypotheses,
        mini_blind_test=_build_mini_blind_test(hypotheses),
        feedback_routes=_build_feedback_routes(hypotheses),
    )


async def export_snapshot(db: DB, interviewee_id: str, out_dir: Path) -> list[Path]:
    bundle = await build_snapshot_bundle(db, interviewee_id)
    target = out_dir / interviewee_id / "snapshot"
    target.mkdir(parents=True, exist_ok=True)
    files = {
        "SOUL-lite.md": render_soul_lite(bundle),
        "mini-blind-test.md": render_mini_blind_test(bundle),
        "feedback-routing.md": render_feedback_routing(bundle),
    }
    written: list[Path] = []
    for name, content in files.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def render_soul_lite(bundle: SnapshotBundle) -> str:
    lines = [
        f"# SOUL-lite Snapshot: {bundle.interviewee_id}",
        "",
        f"- Schema version: {bundle.schema_version}",
        f"- Generated at: {bundle.generated_at}",
        "- Status: hypothesis draft, not a verified persona",
        "",
        "This file is a first-pass personality hypothesis. Treat every item as",
        "`像 / 不像 / 不確定` feedback material, not as a final truth.",
        "",
        "## Hypotheses",
        "",
    ]
    if not bundle.hypotheses:
        lines.extend(
            [
                "_No usable hypotheses yet._",
                "",
                "Suggested next step: run more interview turns before generating Snapshot.",
            ]
        )
        return "\n".join(lines) + "\n"

    for item in bundle.hypotheses:
        lines.extend(
            [
                f"### {item.id}: {item.dimension.value}",
                "",
                f"**Hypothesis:** {item.hypothesis}",
                "",
                f"- Confidence: {item.confidence}",
                f"- Needs verification: {'yes' if item.needs_verification else 'no'}",
                f"- Missing evidence: {item.missing_evidence}",
                f"- Suggested follow-up: {item.suggested_follow_up}",
                "",
                "Evidence:",
                "",
            ]
        )
        for evidence in item.evidence:
            provenance = _provenance(evidence)
            lines.append(f"- [{evidence.kind}{provenance}] {evidence.content}")
        lines.append("")
    return "\n".join(lines)


def render_mini_blind_test(bundle: SnapshotBundle) -> str:
    lines = [
        f"# Mini Blind Test: {bundle.interviewee_id}",
        "",
        "Goal: produce the first `像不像我` signal from the SOUL-lite draft.",
        "",
        "Operator flow:",
        "",
        "1. For each item, ask the human to write their own response.",
        "2. Ask the persona runtime or operator to draft an answer using SOUL-lite.",
        "3. Shuffle the pair as A/B.",
        "4. Ask the human which one is more like them and why.",
        "5. Route misses using `feedback-routing.md`.",
        "",
        "| ID | Dimension | Scenario | Compare | Notes |",
        "|---|---|---|---|---|",
    ]
    for item in bundle.mini_blind_test:
        lines.append(
            "| "
            f"{item.id} | {item.dimension.value} | {item.scenario} | "
            f"{item.what_to_compare} | {item.evidence_hint} |"
        )
    lines.extend(
        [
            "",
            "Scorecard:",
            "",
            "| ID | More-like answer (A/B) | Why | Route next? |",
            "|---|---|---|---|",
        ]
    )
    for item in bundle.mini_blind_test:
        lines.append(f"| {item.id} |  |  |  |")
    return "\n".join(lines) + "\n"


def render_feedback_routing(bundle: SnapshotBundle) -> str:
    lines = [
        f"# Snapshot Feedback Routing: {bundle.interviewee_id}",
        "",
        "Use this when the user says `這不像我` or `不確定` during Snapshot review.",
        "",
        "| Hypothesis | Dimension | If user rejects it | Suggested follow-up |",
        "|---|---|---|---|",
    ]
    for item in bundle.hypotheses:
        lines.append(
            f"| {item.id} | {item.dimension.value} | "
            f"mark {item.dimension.value} as needing re-interview; inspect evidence provenance | "
            f"{item.suggested_follow_up} |"
        )
    lines.extend(["", "Open routes:", ""])
    for route in bundle.feedback_routes:
        lines.append(f"- {route}")
    return "\n".join(lines) + "\n"


def _build_hypotheses(
    anchors: dict[Dimension, list[Anchor]],
    triples: list[PersonaTriple],
) -> list[SoulLiteHypothesis]:
    candidates = _anchor_candidates(anchors) + _triple_candidates(triples)
    ordered = sorted(candidates, key=lambda item: item.weight, reverse=True)
    selected: list[_Candidate] = []
    seen: set[tuple[Dimension, str]] = set()
    for candidate in ordered:
        key = (candidate.dimension, candidate.content.casefold())
        if key in seen:
            continue
        selected.append(candidate)
        seen.add(key)
        if len(selected) >= 8:
            break

    return [_candidate_to_hypothesis(index, candidate) for index, candidate in enumerate(selected, 1)]


def _anchor_candidates(anchors: dict[Dimension, list[Anchor]]) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for dimension in CORE_DIMENSIONS:
        for anchor in anchors.get(dimension, []):
            content = _clean(anchor.content)
            if not content:
                continue
            weight = _anchor_weight(anchor)
            candidates.append(
                _Candidate(
                    dimension=dimension,
                    content=content,
                    evidence=EvidenceItem(
                        kind="anchor",
                        dimension=dimension,
                        layer=anchor.layer,
                        content=content,
                        source_turn_ids=anchor.source_turn_ids,
                        source_question_ids=anchor.source_question_ids,
                    ),
                    weight=weight,
                )
            )
    return candidates


def _triple_candidates(triples: list[PersonaTriple]) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for triple in triples:
        content = _clean(triple.object)
        if not content:
            continue
        dimension = _dimension_for_triple(triple)
        weight = int(float(triple.confidence) * 10)
        if _has_decision_signal(content) or triple.relation in {"red_line", "value_anchor"}:
            weight += 3
        candidates.append(
            _Candidate(
                dimension=dimension,
                content=content,
                evidence=EvidenceItem(
                    kind=f"triple:{triple.relation}",
                    dimension=dimension,
                    content=content,
                    source_turn_ids=triple.source_turn_ids,
                    confidence=triple.confidence,
                ),
                weight=weight,
            )
        )
    return candidates


def _candidate_to_hypothesis(index: int, candidate: _Candidate) -> SoulLiteHypothesis:
    confidence = _confidence(candidate)
    return SoulLiteHypothesis(
        id=f"H{index}",
        dimension=candidate.dimension,
        hypothesis=_hypothesis_text(candidate),
        confidence=confidence,
        evidence=[candidate.evidence],
        missing_evidence=_missing_evidence(candidate, confidence),
        suggested_follow_up=_suggested_follow_up(candidate),
        needs_verification=confidence != "high",
    )


def _build_mini_blind_test(hypotheses: list[SoulLiteHypothesis]) -> list[MiniBlindTestItem]:
    items: list[MiniBlindTestItem] = []
    for index, hypothesis in enumerate(hypotheses[:5], 1):
        items.append(
            MiniBlindTestItem(
                id=f"T{index}",
                dimension=hypothesis.dimension,
                scenario=_scenario_for(hypothesis),
                what_to_compare="Which answer chooses, refuses, or phrases things more like the human?",
                evidence_hint=f"Based on {hypothesis.id}: {hypothesis.hypothesis}",
            )
        )
    return items


def _build_feedback_routes(hypotheses: list[SoulLiteHypothesis]) -> list[str]:
    routes = [
        "If wording feels wrong, route to VOICE and collect 2-3 message samples.",
        "If a value feels wrong, route to SOUL and ask for a concrete counterexample.",
        "If a refusal feels wrong, route to BOUNDARIES and ask when the user would make an exception.",
    ]
    weak_dimensions = sorted({item.dimension.value for item in hypotheses if item.needs_verification})
    if weak_dimensions:
        routes.append(f"Needs verification in: {', '.join(weak_dimensions)}.")
    return routes


def _anchor_weight(anchor: Anchor) -> int:
    weight = 0
    if anchor.triangulated:
        weight += 10
    weight += {Layer.PRINCIPLE: 6, Layer.PATTERN: 4, Layer.FACT: 2}[anchor.layer]
    weight += min(len(set(anchor.source_question_ids)), 3)
    if _has_decision_signal(anchor.content):
        weight += 3
    return weight


def _confidence(candidate: _Candidate) -> str:
    if candidate.weight >= 16:
        return "high"
    if candidate.weight >= 10:
        return "medium"
    return "low"


def _hypothesis_text(candidate: _Candidate) -> str:
    prefix = {
        Dimension.SOUL: "Likely value / identity pattern",
        Dimension.BOUNDARIES: "Likely boundary condition",
        Dimension.VOICE: "Likely voice pattern",
        Dimension.SKILL: "Likely working style",
        Dimension.PEOPLE: "Likely relationship pattern",
        Dimension.HISTORY: "Likely timeline influence",
        Dimension.JOURNAL: "Likely reflection pattern",
        Dimension.STATE: "Likely current-state factor",
    }[candidate.dimension]
    return f"{prefix}: {_clean(candidate.content)}"


def _missing_evidence(candidate: _Candidate, confidence: str) -> str:
    if confidence == "high":
        return "Needs user review, but already has stronger provenance than a single statement."
    if _has_decision_signal(candidate.content):
        return "Needs at least one counterexample or pressure case to verify this decision pattern."
    return "Needs a concrete incident, tradeoff, or repeated occurrence before treating this as stable."


def _suggested_follow_up(candidate: _Candidate) -> str:
    if _has_decision_signal(candidate.content):
        return "Tell me about a recent case where this changed what you chose or refused."
    if candidate.dimension == Dimension.VOICE:
        return "Show me the exact message you would send in this situation."
    if candidate.dimension == Dimension.BOUNDARIES:
        return "When would you make an exception to this boundary, if ever?"
    return "What is one concrete moment that proves this is really how you operate?"


def _scenario_for(hypothesis: SoulLiteHypothesis) -> str:
    scenarios = {
        Dimension.SOUL: "A collaborator asks you to choose between keeping peace and saying what you believe is true.",
        Dimension.BOUNDARIES: "Someone asks for a favor that violates one of your stated boundaries.",
        Dimension.VOICE: "You need to send a short LINE message about a frustrating situation.",
        Dimension.SKILL: "A project is behind schedule and the first plan is not working.",
        Dimension.PEOPLE: "A partner's reliability is uncertain and you need to decide how much to trust them.",
    }
    return scenarios.get(
        hypothesis.dimension,
        "A realistic situation tests whether this hypothesis changes what you would say or choose.",
    )


def _dimension_for_triple(triple: PersonaTriple) -> Dimension:
    relation = triple.relation.lower()
    text = triple.object.lower()
    if relation == "red_line" or any(word in text for word in ("boundary", "refuse", "底線", "拒絕")):
        return Dimension.BOUNDARIES
    if relation == "skill":
        return Dimension.SKILL
    if any(word in text for word in ("say", "voice", "message", "語氣", "訊息")):
        return Dimension.VOICE
    if any(word in text for word in ("relationship", "trust", "people", "信任", "關係")):
        return Dimension.PEOPLE
    return Dimension.SOUL


def _has_decision_signal(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in DECISION_KEYWORDS)


def _clean(text: str) -> str:
    return scrub_pii(text).scrubbed_text.strip()


def _provenance(evidence: EvidenceItem) -> str:
    parts: list[str] = []
    if evidence.layer is not None:
        parts.append(evidence.layer.value)
    if evidence.confidence is not None:
        parts.append(f"confidence={evidence.confidence:.2f}")
    if evidence.source_question_ids:
        parts.append(f"questions={','.join(evidence.source_question_ids)}")
    if evidence.source_turn_ids:
        turns = ",".join(str(turn_id) for turn_id in evidence.source_turn_ids)
        parts.append(f"turns={turns}")
    return f"; {'; '.join(parts)}" if parts else ""

