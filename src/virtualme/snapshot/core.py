from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from virtualme.interview.pii import scrub_pii
from virtualme.interview.triples import PersonaTriple
from virtualme.storage.db import DB, Anchor, Dimension, Layer

SNAPSHOT_SCHEMA_VERSION = "0.1"

ReviewVerdict = Literal["like_me", "unlike_me", "unsure", "missing_context"]
ReviewEvidenceQuality = Literal["none", "low", "medium", "medium_high", "high"]

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

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "when",
    "with",
    "you",
    "your",
    "而",
    "的",
    "了",
    "和",
    "是",
    "在",
    "我",
    "你",
    "他",
    "她",
    "它",
}

warnings.filterwarnings(
    "ignore",
    message='Field name "register" in "ConstructCard" shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)


class EvidenceItem(BaseModel):
    kind: str
    dimension: Dimension | None = None
    layer: Layer | None = None
    content: str
    source_anchor_ids: list[int] = Field(default_factory=list)
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


class ConstructCard(BaseModel):
    id: str
    title: str
    decision_rule: str
    trigger_context: str
    protected_value: str
    traded_value: str | None = None
    default_action: str
    refused_action: str | None = None
    exception_rule: str | None = None
    register: str | None = None
    falsifier: str
    supporting_evidence: list[EvidenceItem]
    disconfirming_evidence: list[EvidenceItem]
    source_anchor_ids: list[int]
    source_turn_ids: list[int]
    source_question_ids: list[str]
    dimension_tags: list[Dimension]
    confidence_level: Literal["insufficient", "draft", "plausible", "validated"]
    confidence_reason: str
    confidence_checks: dict[str, bool]
    missing_evidence: list[str]
    blind_test_probe: str | None = None
    feedback_routes: list[str]
    extraction_method: Literal["rule_based", "llm_assisted", "human_curated"]
    policy_status: Literal["espoused_only", "behavior_supported", "contradicted", "validated"]
    stability_scope: str | None = None
    context_dependence: str | None = None
    exception_archetype: Literal[
        "relational_credit",
        "asymmetric_leverage",
        "operational_reciprocity",
    ] | None = None


class ConstructCardReview(BaseModel):
    card_id: str
    verdict: ReviewVerdict
    reviewer: str | None = None
    reviewed_at: str | None = None
    notes: str | None = None
    concrete_case: str | None = None
    exception_note: str | None = None
    counterexample_note: str | None = None
    exact_wording_note: str | None = None
    pressure_note: str | None = None
    decision_tradeoff_note: str | None = None
    evidence_quality: ReviewEvidenceQuality = "none"
    status_after_review: str | None = None
    confidence_level: Literal["insufficient", "draft", "plausible", "validated"] | None = None
    policy_status: Literal["espoused_only", "behavior_supported", "contradicted", "validated"] | None = None


class SnapshotBundle(BaseModel):
    schema_version: str = SNAPSHOT_SCHEMA_VERSION
    interviewee_id: str
    generated_at: str
    construct_cards: list[ConstructCard]
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
    construct_cards = _build_construct_cards(hypotheses)
    return SnapshotBundle(
        interviewee_id=interviewee_id,
        generated_at=generated_at,
        construct_cards=construct_cards,
        hypotheses=hypotheses,
        mini_blind_test=_build_mini_blind_test(construct_cards, hypotheses),
        feedback_routes=_build_feedback_routes(construct_cards, hypotheses),
    )


async def export_snapshot(db: DB, interviewee_id: str, out_dir: Path) -> list[Path]:
    bundle = await build_snapshot_bundle(db, interviewee_id)
    return export_snapshot_bundle(bundle, out_dir)


async def export_snapshot_with_review(
    db: DB,
    interviewee_id: str,
    out_dir: Path,
    review_path: Path,
) -> list[Path]:
    bundle = await build_snapshot_bundle(db, interviewee_id)
    reviews = load_construct_card_reviews(review_path)
    bundle = apply_construct_card_reviews(bundle, reviews)
    return export_snapshot_bundle(bundle, out_dir, reviews=reviews)


def export_snapshot_bundle(
    bundle: SnapshotBundle,
    out_dir: Path,
    reviews: list[ConstructCardReview] | None = None,
) -> list[Path]:
    from virtualme.snapshot.behavior_profile import render_behavior_profile

    target = out_dir / bundle.interviewee_id / "snapshot"
    target.mkdir(parents=True, exist_ok=True)
    files = {
        "behavior-profile.md": render_behavior_profile(bundle),
        "construct-cards.md": render_construct_cards(bundle),
        "SOUL-lite.md": render_soul_lite(bundle),
        "mini-blind-test.md": render_mini_blind_test(bundle),
        "feedback-routing.md": render_feedback_routing(bundle),
    }
    if reviews is not None:
        files["construct-card-review-summary.md"] = render_construct_card_review_summary(
            bundle,
            reviews,
        )
    written: list[Path] = []
    for name, content in files.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def load_construct_card_reviews(path: Path) -> list[ConstructCardReview]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
        if isinstance(raw, dict):
            raw = raw.get("reviews", raw.get("cards", []))
        return [ConstructCardReview.model_validate(item) for item in raw]
    return _load_markdown_construct_card_reviews(text)


def apply_construct_card_reviews(
    bundle: SnapshotBundle,
    reviews: list[ConstructCardReview],
) -> SnapshotBundle:
    review_by_card = {review.card_id.upper(): review for review in reviews}
    cards = [
        _apply_construct_card_review(card, review_by_card.get(card.id.upper()))
        for card in bundle.construct_cards
    ]
    return bundle.model_copy(update={"construct_cards": cards})


def render_construct_card_review_summary(
    bundle: SnapshotBundle,
    reviews: list[ConstructCardReview],
) -> str:
    review_by_card = {review.card_id.upper(): review for review in reviews}
    lines = [
        f"# Construct Card Review Summary: {bundle.interviewee_id}",
        "",
        f"- Schema version: {bundle.schema_version}",
        f"- Generated at: {bundle.generated_at}",
        "- Status: human review ingestion summary; not a validation certificate",
        "",
        "| Card | Verdict | Confidence | Policy status | Evidence quality | Status after review | Remaining missing evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for card in bundle.construct_cards:
        review = review_by_card.get(card.id.upper())
        lines.append(
            f"| {card.id} | {review.verdict if review else 'unreviewed'} | "
            f"{card.confidence_level} | {card.policy_status} | "
            f"{review.evidence_quality if review else 'none'} | "
            f"{review.status_after_review or 'not specified' if review else 'not reviewed'} | "
            f"{', '.join(card.missing_evidence) or 'none'} |"
        )
    lines.extend(["", "Review notes:", ""])
    for review in reviews:
        lines.append(f"## {review.card_id}: {review.verdict}")
        lines.append("")
        for label, value in _review_note_items(review):
            lines.append(f"- {label}: {value}")
        lines.append("")
    return "\n".join(lines)


def _load_markdown_construct_card_reviews(text: str) -> list[ConstructCardReview]:
    reviewer = _first_markdown_value(text, "Reviewer")
    reviewed_at = _first_markdown_value(text, "Date")
    espoused_only_ids = set()
    if re.search(r"C5\s+(?:為|is)\s+espoused", text, flags=re.IGNORECASE):
        espoused_only_ids.add("C5")

    sections = re.split(r"(?m)^\s*###\s+", text)
    reviews: list[ConstructCardReview] = []
    for section in sections[1:]:
        header, _, body = section.partition("\n")
        match = re.match(r"(C\d+)\b(.*)", header.strip())
        if match is None:
            continue
        card_id = match.group(1).upper()
        header_tail = match.group(2)
        confidence = _markdown_confidence(header_tail)
        verdict = _markdown_verdict(body, confidence)
        evidence_line = _markdown_evidence_line(body)
        review = ConstructCardReview(
            card_id=card_id,
            verdict=verdict,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
            notes=evidence_line,
            exception_note=_markdown_category_note(evidence_line, ("exception", "例外", "unless")),
            counterexample_note=_markdown_category_note(evidence_line, ("counterexample", "反例")),
            exact_wording_note=_markdown_category_note(
                evidence_line,
                ("wording", "實錄", "話術", "quote"),
            ),
            pressure_note=_markdown_category_note(evidence_line, ("pressure", "壓力", "高風險")),
            decision_tradeoff_note=_markdown_category_note(
                evidence_line,
                ("tradeoff", "取捨", "選擇題", "問卷"),
            ),
            evidence_quality=_markdown_evidence_quality(body),
            confidence_level=confidence,
            policy_status="espoused_only" if card_id in espoused_only_ids else None,
            status_after_review=f"markdown_ingested_{confidence}" if confidence else None,
        )
        reviews.append(review)
    return reviews


def _apply_construct_card_review(
    card: ConstructCard,
    review: ConstructCardReview | None,
) -> ConstructCard:
    if review is None:
        return card

    confidence_level = _review_confidence_level(card, review)
    policy_status = _review_policy_status(card, review)
    missing_evidence = _remaining_missing_evidence(card.missing_evidence, review)
    confidence_checks = {
        **card.confidence_checks,
        "human_reviewed": True,
        "human_confirmed": review.verdict == "like_me",
        "review_has_concrete_case": bool(_text_value(review.concrete_case)),
        "review_has_exception_or_counterexample": bool(
            _text_value(review.exception_note) or _text_value(review.counterexample_note)
        ),
        "review_has_pressure": bool(_text_value(review.pressure_note)),
    }
    supporting_evidence = list(card.supporting_evidence)
    disconfirming_evidence = list(card.disconfirming_evidence)
    review_evidence = EvidenceItem(
        kind="human_review",
        content=_review_evidence_content(review),
    )
    if review.verdict == "unlike_me":
        disconfirming_evidence.append(review_evidence)
    else:
        supporting_evidence.append(review_evidence)

    return card.model_copy(
        update={
            "confidence_level": confidence_level,
            "confidence_reason": _review_confidence_reason(card, review, confidence_level),
            "confidence_checks": confidence_checks,
            "missing_evidence": missing_evidence,
            "policy_status": policy_status,
            "supporting_evidence": supporting_evidence,
            "disconfirming_evidence": disconfirming_evidence,
        }
    )


def _review_confidence_level(
    card: ConstructCard,
    review: ConstructCardReview,
) -> Literal["insufficient", "draft", "plausible", "validated"]:
    if review.verdict == "unlike_me":
        return "insufficient"
    if review.verdict in {"unsure", "missing_context"}:
        return card.confidence_level
    if review.confidence_level is not None:
        return "plausible" if review.confidence_level == "validated" else review.confidence_level
    if review.evidence_quality in {"medium", "medium_high", "high"}:
        return "plausible"
    if _text_value(review.concrete_case) and (
        _text_value(review.pressure_note)
        or _text_value(review.exception_note)
        or _text_value(review.counterexample_note)
    ):
        return "plausible"
    return "draft"


def _review_policy_status(
    card: ConstructCard,
    review: ConstructCardReview,
) -> Literal["espoused_only", "behavior_supported", "contradicted", "validated"]:
    if review.verdict == "unlike_me":
        return "contradicted"
    if review.policy_status is not None:
        return "behavior_supported" if review.policy_status == "validated" else review.policy_status
    if _text_value(review.concrete_case) or review.evidence_quality in {"medium", "medium_high", "high"}:
        return "behavior_supported"
    return card.policy_status


def _review_confidence_reason(
    card: ConstructCard,
    review: ConstructCardReview,
    confidence_level: str,
) -> str:
    parts = [card.confidence_reason, f"human review verdict={review.verdict}"]
    if review.evidence_quality != "none":
        parts.append(f"review evidence quality={review.evidence_quality}")
    if review.status_after_review:
        parts.append(f"status after review={review.status_after_review}")
    if confidence_level == "plausible":
        parts.append("raised by offline review ingestion, not runtime validation")
    if confidence_level == "draft" and review.verdict == "like_me":
        parts.append("human-confirmed draft without enough behavioral audit")
    return "; ".join(part for part in parts if part)


def _remaining_missing_evidence(
    missing_evidence: list[str],
    review: ConstructCardReview,
) -> list[str]:
    resolved = set()
    if _text_value(review.exception_note):
        resolved.add("exception")
    if _text_value(review.counterexample_note):
        resolved.add("counterexample")
    if _text_value(review.exact_wording_note):
        resolved.add("exact_wording")
    if _text_value(review.pressure_note):
        resolved.add("pressure")
    if _text_value(review.decision_tradeoff_note):
        resolved.add("decision_tradeoff")
    return [item for item in missing_evidence if item not in resolved]


def _review_evidence_content(review: ConstructCardReview) -> str:
    parts = [f"verdict={review.verdict}", f"evidence_quality={review.evidence_quality}"]
    if review.reviewer:
        parts.append(f"reviewer={review.reviewer}")
    if review.reviewed_at:
        parts.append(f"reviewed_at={review.reviewed_at}")
    if review.status_after_review:
        parts.append(f"status={review.status_after_review}")
    note_values = [value for _, value in _review_note_items(review)]
    if note_values:
        parts.append("notes=" + " | ".join(note_values))
    return _clean("; ".join(parts))


def _review_note_items(review: ConstructCardReview) -> list[tuple[str, str]]:
    fields = [
        ("reviewer", review.reviewer),
        ("reviewed_at", review.reviewed_at),
        ("status_after_review", review.status_after_review),
        ("notes", review.notes),
        ("concrete_case", review.concrete_case),
        ("exception_note", review.exception_note),
        ("counterexample_note", review.counterexample_note),
        ("pressure_note", review.pressure_note),
        ("exact_wording_note", review.exact_wording_note),
        ("decision_tradeoff_note", review.decision_tradeoff_note),
    ]
    return [(label, _clean(value)) for label, value in fields if _text_value(value)]


def _first_markdown_value(text: str, label: str) -> str | None:
    match = re.search(rf"(?m)^\*\*{re.escape(label)}\*\*\s*:\s*(.+)$", text)
    if match is None:
        match = re.search(rf"(?m)^{re.escape(label)}\s*:\s*(.+)$", text)
    return _clean(match.group(1)) if match else None


def _markdown_confidence(header: str) -> Literal["insufficient", "draft", "plausible", "validated"] | None:
    match = re.search(r"confidence:\s*(insufficient|draft|plausible|validated)", header)
    return match.group(1) if match else None  # type: ignore[return-value]


def _markdown_verdict(
    body: str,
    confidence: str | None,
) -> ReviewVerdict:
    if re.search(r"\[[VXx✓]\]\s*像我", body):
        return "like_me"
    if re.search(r"\[[VXx✓]\]\s*不像我", body):
        return "unlike_me"
    if re.search(r"\[[VXx✓]\]\s*不確定", body):
        return "unsure"
    if re.search(r"\[[VXx✓]\]\s*缺脈絡", body):
        return "missing_context"
    if confidence in {"plausible", "validated"}:
        return "like_me"
    return "unsure"


def _markdown_evidence_line(body: str) -> str | None:
    match = re.search(r"(?m)^-\s*證據\s*[\uff1a:]\s*(.+)$", body)
    return _clean(match.group(1)) if match else None


def _markdown_evidence_quality(body: str) -> ReviewEvidenceQuality:
    if re.search(r"證據\s*[\uff1a:].+", body):
        return "medium"
    return "none"


def _markdown_category_note(text: str | None, keywords: tuple[str, ...]) -> str | None:
    if text and _contains_any(text, keywords):
        return text
    return None


def _text_value(value: str | None) -> bool:
    return bool(value and value.strip())


def render_soul_lite(bundle: SnapshotBundle) -> str:
    low_confidence_count = sum(1 for item in bundle.hypotheses if item.confidence == "low")
    lines = [
        f"# SOUL-lite Snapshot: {bundle.interviewee_id}",
        "",
        f"- Schema version: {bundle.schema_version}",
        f"- Generated at: {bundle.generated_at}",
        "- Status: hypothesis draft, not a verified persona",
        f"- Quality warning: {_quality_warning(bundle)}",
        "",
        "This file is a first-pass personality hypothesis. Treat every item as",
        "`像 / 不像 / 不確定` feedback material, not as a final truth.",
        "",
        "## Top-Level Sketch",
        "",
        *_top_level_sketch(bundle),
        "",
        "## Review Priority",
        "",
        f"- Low-confidence hypotheses: {low_confidence_count}/{len(bundle.hypotheses)}",
        f"- First blind-test target: {_first_review_target(bundle)}",
        "- Pass condition: the human can name why one answer is more like them, not just pick A/B.",
        "",
        "## Synthesized Patterns",
        "",
    ]
    if bundle.construct_cards:
        for card in bundle.construct_cards:
            lines.extend(
                [
                    f"### {card.id}: {card.title}",
                    "",
                    f"**Decision rule:** {card.decision_rule}",
                    "",
                    f"- Trigger context: {card.trigger_context}",
                    f"- Protected value: {card.protected_value}",
                    f"- Traded value: {card.traded_value or 'unknown'}",
                    f"- Default action: {card.default_action}",
                    f"- Refused action: {card.refused_action or 'unknown'}",
                    f"- Exception rule: {card.exception_rule or 'unknown'}",
                    f"- Policy status: {card.policy_status}",
                    f"- Confidence: {card.confidence_level} ({card.confidence_reason})",
                    f"- Falsifier: {card.falsifier}",
                    f"- Missing evidence: {', '.join(card.missing_evidence) or 'none'}",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "_No construct cards yet._",
                "",
                "Suggested next step: collect pressure, exception, and decision-tradeoff evidence.",
                "",
            ]
        )
    lines.extend(
        [
            "## Raw Hypotheses Appendix",
            "",
            "These are source-level hypotheses retained for audit. They are no longer the primary extraction unit.",
            "",
        ]
    )
    if not bundle.hypotheses:
        lines.extend(
            [
                "_No usable raw hypotheses yet._",
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


def render_construct_cards(bundle: SnapshotBundle) -> str:
    lines = [
        f"# Construct Cards: {bundle.interviewee_id}",
        "",
        f"- Schema version: {bundle.schema_version}",
        f"- Generated at: {bundle.generated_at}",
        "- Status: mechanism-first behavioral policy hypotheses, not verified personality truth",
        "",
    ]
    if not bundle.construct_cards:
        lines.extend(
            [
                "_No construct cards generated._",
                "",
                "Collect decision tradeoff, pressure, exception, and counterexample evidence.",
            ]
        )
        return "\n".join(lines) + "\n"

    for card in bundle.construct_cards:
        lines.extend(
            [
                f"## {card.id}: {card.title}",
                "",
                f"- Decision rule: {card.decision_rule}",
                f"- Trigger context: {card.trigger_context}",
                f"- Protected value: {card.protected_value}",
                f"- Traded value: {card.traded_value or 'unknown'}",
                f"- Default action: {card.default_action}",
                f"- Refused action: {card.refused_action or 'unknown'}",
                f"- Exception rule: {card.exception_rule or 'unknown'}",
                f"- Register: {card.register or 'unknown'}",
                f"- Falsifier: {card.falsifier}",
                f"- Dimension tags: {', '.join(dimension.value for dimension in card.dimension_tags)}",
                f"- Confidence: {card.confidence_level}",
                f"- Confidence reason: {card.confidence_reason}",
                f"- Policy status: {card.policy_status}",
                f"- Stability scope: {card.stability_scope or 'unknown'}",
                f"- Context dependence: {card.context_dependence or 'unknown'}",
                f"- Exception archetype: {card.exception_archetype or 'unknown'}",
                f"- Extraction method: {card.extraction_method}",
                f"- Missing evidence: {', '.join(card.missing_evidence) or 'none'}",
                f"- Feedback routes: {', '.join(card.feedback_routes) or 'none'}",
                f"- Blind-test probe: {card.blind_test_probe or 'unknown'}",
                "",
                "Confidence checks:",
                "",
            ]
        )
        for name, passed in card.confidence_checks.items():
            lines.append(f"- {name}: {'yes' if passed else 'no'}")
        lines.extend(["", "Supporting evidence:", ""])
        for evidence in card.supporting_evidence:
            lines.append(f"- [{evidence.kind}{_provenance(evidence)}] {evidence.content}")
        if card.disconfirming_evidence:
            lines.extend(["", "Disconfirming evidence:", ""])
            for evidence in card.disconfirming_evidence:
                lines.append(f"- [{evidence.kind}{_provenance(evidence)}] {evidence.content}")
        else:
            lines.extend(["", "Disconfirming evidence:", "", "- unknown"])
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
        "| ID | Dimension | Concrete scenario | A/B prompt | Must compare | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for item in bundle.mini_blind_test:
        lines.append(
            "| "
            f"{item.id} | {item.dimension.value} | {item.scenario} | "
            "Draft two 3-5 sentence answers: one human answer, one persona answer. | "
            f"{item.what_to_compare} | {item.evidence_hint} |"
        )
    lines.extend(
        [
            "",
            "Scorecard:",
            "",
            "| ID | More-like answer (A/B) | Exact unlike-me phrase | Missing decision signal | Route next? |",
            "|---|---|---|---|---|",
        ]
    )
    for item in bundle.mini_blind_test:
        lines.append(f"| {item.id} |  |  |  |  |")
    return "\n".join(lines) + "\n"


def render_feedback_routing(bundle: SnapshotBundle) -> str:
    lines = [
        f"# Snapshot Feedback Routing: {bundle.interviewee_id}",
        "",
        "Use this when the user says `這不像我` or `不確定` during Snapshot review.",
        "",
        "## Construct Card Routes",
        "",
        "| Card | Dimensions | Missing evidence | Counterexample | Pressure | Exception | Exact wording | Decision tradeoff |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for card in bundle.construct_cards:
        routes = set(card.feedback_routes)
        lines.append(
            f"| {card.id} | {', '.join(dimension.value for dimension in card.dimension_tags)} | "
            f"{', '.join(card.missing_evidence) or 'none'} | "
            f"{_card_route(routes, 'counterexample')} | "
            f"{_card_route(routes, 'pressure')} | "
            f"{_card_route(routes, 'exception')} | "
            f"{_card_route(routes, 'exact_wording')} | "
            f"{_card_route(routes, 'decision_tradeoff')} |"
        )
    lines.extend(
        [
            "",
            "## Raw Hypothesis Appendix Routes",
            "",
            "| Hypothesis | Dimension | If user rejects it | Counterexample to collect | Pressure signal | Exception signal | Exact wording signal | Decision tradeoff signal |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for item in bundle.hypotheses:
        lines.append(
            f"| {item.id} | {item.dimension.value} | "
            f"mark {item.dimension.value} as needing re-interview; inspect evidence provenance | "
            f"{_counterexample_signal(item)} | "
            f"{_pressure_signal(item)} | "
            f"{_exception_signal(item)} | "
            f"{_exact_wording_signal(item)} | "
            f"{_decision_tradeoff_signal(item)} |"
        )
    lines.extend(["", "Open routes:", ""])
    for route in bundle.feedback_routes:
        lines.append(f"- {route}")
    return "\n".join(lines) + "\n"


def _quality_warning(bundle: SnapshotBundle) -> str:
    if not bundle.hypotheses:
        return "no hypotheses yet; do not run blind test"
    low_count = sum(1 for item in bundle.hypotheses if item.confidence == "low")
    high_count = sum(1 for item in bundle.hypotheses if item.confidence == "high")
    if low_count == len(bundle.hypotheses):
        return "all hypotheses are low confidence; use only for targeted follow-up"
    if high_count == 0:
        return "no high-confidence hypothesis yet; require mini blind test before persona use"
    if low_count:
        return f"{low_count} low-confidence hypotheses need focused follow-up"
    return "usable as a review draft after human confirmation"


def _top_level_sketch(bundle: SnapshotBundle) -> list[str]:
    if not bundle.hypotheses:
        return ["_No sketch yet._"]

    by_dimension: dict[Dimension, SoulLiteHypothesis] = {}
    for item in bundle.hypotheses:
        by_dimension.setdefault(item.dimension, item)
    lines = [
        f"- Core decision default: {_sketch_phrase(by_dimension.get(Dimension.SOUL))}",
        f"- Boundary / refusal pattern: {_sketch_phrase(by_dimension.get(Dimension.BOUNDARIES))}",
        f"- Communication surface: {_sketch_phrase(by_dimension.get(Dimension.VOICE))}",
        f"- Work / capability pattern: {_sketch_phrase(by_dimension.get(Dimension.SKILL))}",
        f"- Trust / people pattern: {_sketch_phrase(by_dimension.get(Dimension.PEOPLE))}",
    ]
    strongest = bundle.hypotheses[0]
    lines.append(
        f"- Strongest current signal: {strongest.id} ({strongest.dimension.value}, "
        f"{strongest.confidence})"
    )
    return lines


def _sketch_phrase(hypothesis: SoulLiteHypothesis | None) -> str:
    if hypothesis is None:
        return "unknown; needs interview evidence"
    return f"{_strip_hypothesis_prefix(hypothesis.hypothesis)} ({hypothesis.id}, {hypothesis.confidence})"


def _strip_hypothesis_prefix(text: str) -> str:
    _, separator, tail = text.partition(": ")
    return tail if separator else text


def _first_review_target(bundle: SnapshotBundle) -> str:
    if not bundle.mini_blind_test:
        return "none"
    first = bundle.mini_blind_test[0]
    return f"{first.id} / {first.dimension.value}"


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
                        source_anchor_ids=[anchor.id] if anchor.id is not None else [],
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


def _build_construct_cards(hypotheses: list[SoulLiteHypothesis]) -> list[ConstructCard]:
    families = (
        _triangle_construct,
        _direct_conflict_construct,
        _handoff_construct,
        _emotional_blackmail_construct,
        _attacker_motive_construct,
    )
    cards: list[ConstructCard] = []
    used_hypotheses: set[str] = set()
    for build_family in families:
        matches = [item for item in hypotheses if build_family(item) is not None]
        matches = [item for item in matches if item.id not in used_hypotheses]
        if not matches:
            continue
        card = build_family(matches[0])
        if card is None:
            continue
        card = _finalize_construct_card(card)
        cards.append(card.model_copy(update={"id": f"C{len(cards) + 1}"}))
        used_hypotheses.update(item.id for item in matches)
    return cards


def _triangle_construct(hypothesis: SoulLiteHypothesis) -> ConstructCard | None:
    text = _card_source_text(hypothesis)
    if not _contains_any(text, ("鐵三角", "時程", "範疇", "預算", "triangle", "budget", "scope", "schedule")):
        return None
    return _construct_from_hypothesis(
        hypothesis,
        title="Constraint triangle integrity",
        decision_rule=(
            "When constraints are mutually inconsistent, protect delivery realism by making the "
            "tradeoff explicit and renegotiating one side of the triangle."
        ),
        trigger_context="A plan asks for fixed outcome, fixed resources, and fixed timing at once.",
        protected_value="delivery realism",
        traded_value="short-term harmony",
        default_action="surface the constraint conflict and ask which condition can move",
        refused_action="pretend all constraints can stay unchanged",
        exception_rule=None,
        falsifier="Accepts an impossible plan to preserve harmony without naming the tradeoff.",
        blind_test_probe=(
            "A family event has a fixed date, limited helpers, and a larger guest list than the "
            "space can handle. Write how you would reset the plan."
        ),
        dimension_tags=[Dimension.SKILL, Dimension.BOUNDARIES, Dimension.SOUL],
        missing_evidence=["exception", "counterexample"],
        feedback_routes=["exception", "counterexample", "decision_tradeoff", "pressure"],
        stability_scope="project-like coordination under visible constraints",
        context_dependence="strongest when tradeoffs affect delivery or operational credibility",
    )


def _direct_conflict_construct(hypothesis: SoulLiteHypothesis) -> ConstructCard | None:
    text = _card_source_text(hypothesis)
    if not _contains_any(text, ("direct", "truth", "conflict", "invalid", "不合理", "衝突", "失效", "風險")):
        return None
    return _construct_from_hypothesis(
        hypothesis,
        title="Invalid-condition confrontation",
        decision_rule=(
            "When a working condition is invalid, protect truthfulness and delivery by naming "
            "the problem directly before smoothing the relationship."
        ),
        trigger_context="A situation remains socially smoother if the invalid condition is left unnamed.",
        protected_value="truthful diagnosis",
        traded_value="immediate social comfort",
        default_action="state the invalid condition and the operational consequence",
        refused_action="keep peace by leaving the core problem ambiguous",
        exception_rule=None,
        falsifier="Chooses vague reassurance when the condition itself makes success impossible.",
        blind_test_probe=(
            "A volunteer team promises a public event but the venue access, staffing, and timing "
            "cannot work together. Write the first message you would send."
        ),
        dimension_tags=[Dimension.SOUL, Dimension.VOICE, Dimension.BOUNDARIES],
        missing_evidence=["exception", "exact_wording", "counterexample"],
        feedback_routes=["exception", "exact_wording", "counterexample", "pressure"],
        stability_scope="high-risk coordination and accountability moments",
        context_dependence="weaker when directness would expose private information unnecessarily",
    )


def _handoff_construct(hypothesis: SoulLiteHypothesis) -> ConstructCard | None:
    text = _card_source_text(hypothesis)
    if not _contains_any(text, ("交接班", "交接", "投入", "handoff", "commitment")):
        return None
    return _construct_from_hypothesis(
        hypothesis,
        title="Handoff as commitment signal",
        decision_rule=(
            "When ownership is transferred, protect operational continuity by treating handoff "
            "quality as evidence of real commitment."
        ),
        trigger_context="Someone claims they are done but the next operator lacks usable context.",
        protected_value="operational continuity",
        traded_value="trust based only on stated intent",
        default_action="inspect the handoff artifact before accepting the commitment signal",
        refused_action="accept verbal completion without usable transfer details",
        exception_rule=None,
        falsifier="Treats a vague handoff as sufficient commitment during a consequential transfer.",
        blind_test_probe=(
            "A community kitchen changes shifts before a large meal, but the departing lead leaves "
            "only a vague note. Decide whether to accept it or intervene."
        ),
        dimension_tags=[Dimension.SKILL, Dimension.PEOPLE],
        missing_evidence=["exception", "pressure", "counterexample"],
        feedback_routes=["exception", "pressure", "counterexample"],
        stability_scope="work handoffs and responsibility transfer",
        context_dependence="strongest when another person must act from the transferred context",
        exception_archetype="operational_reciprocity",
    )


def _emotional_blackmail_construct(hypothesis: SoulLiteHypothesis) -> ConstructCard | None:
    text = _card_source_text(hypothesis)
    if not _contains_any(text, ("情感勒索", "議價", "報價", "blackmail", "pricing", "negotiation", "discount")):
        return None
    return _construct_from_hypothesis(
        hypothesis,
        title="Emotional-pressure pricing boundary",
        decision_rule=(
            "When a negotiation uses relationship pressure, protect fair exchange by separating "
            "emotional claims from the actual terms."
        ),
        trigger_context="A counterpart frames a concession as proof of loyalty, friendship, or care.",
        protected_value="fair exchange",
        traded_value="approval from the counterpart",
        default_action="return the conversation to terms, value, and viable alternatives",
        refused_action="grant concessions because affection or loyalty was invoked",
        exception_rule=None,
        falsifier="Gives a concession mainly to avoid being framed as uncaring or disloyal.",
        blind_test_probe=(
            "A relative asks you to absorb extra planning work for a shared trip because family "
            "should help family. Write how you separate care from the actual arrangement."
        ),
        dimension_tags=[Dimension.BOUNDARIES, Dimension.PEOPLE, Dimension.VOICE],
        missing_evidence=["exception", "exact_wording", "counterexample"],
        feedback_routes=["exception", "exact_wording", "counterexample", "decision_tradeoff"],
        stability_scope="negotiations where relational pressure distorts terms",
        context_dependence="weaker when there is explicit prior reciprocity or care obligation",
        exception_archetype="relational_credit",
    )


def _attacker_motive_construct(hypothesis: SoulLiteHypothesis) -> ConstructCard | None:
    text = _card_source_text(hypothesis)
    if not _contains_any(text, ("陷害", "人性", "目的", "motive", "attacker", "attribution", "undermine")):
        return None
    return _construct_from_hypothesis(
        hypothesis,
        title="Action over attribution",
        decision_rule=(
            "When harm or sabotage is possible, protect agency by acting on observable impact "
            "instead of over-investing in motive attribution."
        ),
        trigger_context="The other person's intent is ambiguous but the effect is already consequential.",
        protected_value="practical agency",
        traded_value="certainty about hidden motives",
        default_action="respond to the observable behavior and impact first",
        refused_action="delay action until the motive is fully explained",
        exception_rule=None,
        falsifier="Spends the main effort proving motive while leaving the practical risk unresolved.",
        blind_test_probe=(
            "A neighborhood group keeps missing promised tasks and your plan is affected. Decide "
            "whether to investigate intent, redesign the dependency, or confront the behavior."
        ),
        dimension_tags=[Dimension.SOUL, Dimension.PEOPLE],
        missing_evidence=["exception", "counterexample", "pressure"],
        feedback_routes=["exception", "counterexample", "pressure"],
        stability_scope="ambiguous-conflict cases where motives are hard to verify",
        context_dependence="weaker when legal, safety, or trust repair requires motive evidence",
    )


def _construct_from_hypothesis(
    hypothesis: SoulLiteHypothesis,
    *,
    title: str,
    decision_rule: str,
    trigger_context: str,
    protected_value: str,
    traded_value: str | None,
    default_action: str,
    refused_action: str | None,
    exception_rule: str | None,
    falsifier: str,
    blind_test_probe: str | None,
    dimension_tags: list[Dimension],
    missing_evidence: list[str],
    feedback_routes: list[str],
    stability_scope: str | None,
    context_dependence: str | None,
    exception_archetype: Literal[
        "relational_credit",
        "asymmetric_leverage",
        "operational_reciprocity",
    ]
    | None = None,
) -> ConstructCard:
    evidence = hypothesis.evidence
    return ConstructCard(
        id="C0",
        title=title,
        decision_rule=decision_rule,
        trigger_context=trigger_context,
        protected_value=protected_value,
        traded_value=traded_value,
        default_action=default_action,
        refused_action=refused_action,
        exception_rule=exception_rule,
        register=None,
        falsifier=falsifier,
        supporting_evidence=evidence,
        disconfirming_evidence=[],
        source_anchor_ids=_source_anchor_ids(evidence),
        source_turn_ids=_source_turn_ids(evidence),
        source_question_ids=_source_question_ids(evidence),
        dimension_tags=dimension_tags,
        confidence_level="draft",
        confidence_reason="rule-based construct with supporting evidence but no human review",
        confidence_checks={},
        missing_evidence=missing_evidence,
        blind_test_probe=blind_test_probe,
        feedback_routes=feedback_routes,
        extraction_method="rule_based",
        policy_status=_policy_status(evidence),
        stability_scope=stability_scope,
        context_dependence=context_dependence,
        exception_archetype=exception_archetype,
    )


def _finalize_construct_card(card: ConstructCard) -> ConstructCard:
    support_count = len(card.supporting_evidence)
    has_falsifier = bool(card.falsifier.strip())
    has_exception_audit = card.exception_rule is not None or "exception" not in card.missing_evidence
    raw_wrapper_risk = _max_raw_wrapper_overlap(card) > 0.45
    confidence_level: Literal["insufficient", "draft", "plausible", "validated"] = "draft"
    reasons = ["rule-based v0.1 synthesis"]
    if support_count <= 1:
        reasons.append("single-anchor support caps confidence at draft")
    if not has_falsifier:
        confidence_level = "insufficient"
        reasons.append("missing falsifier")
    if not has_exception_audit:
        reasons.append("missing exception or counterexample audit")
    if raw_wrapper_risk:
        confidence_level = "insufficient"
        reasons.append("lexical raw-wrapper risk")
    return card.model_copy(
        update={
            "confidence_level": confidence_level,
            "confidence_reason": "; ".join(reasons),
            "confidence_checks": {
                "has_supporting_evidence": bool(card.supporting_evidence),
                "multi_anchor_support": support_count > 1,
                "has_falsifier": has_falsifier,
                "has_exception_or_counterexample_audit": has_exception_audit,
                "raw_wrapper_safe": not raw_wrapper_risk,
                "human_reviewed": False,
            },
        }
    )


def _build_mini_blind_test(
    construct_cards: list[ConstructCard],
    hypotheses: list[SoulLiteHypothesis],
) -> list[MiniBlindTestItem]:
    items: list[MiniBlindTestItem] = []
    for index, card in enumerate(construct_cards[:5], 1):
        items.append(
            MiniBlindTestItem(
                id=f"T{index}",
                dimension=card.dimension_tags[0],
                scenario=card.blind_test_probe
                or f"Create a new-domain pressure case for `{card.decision_rule}`.",
                what_to_compare="Which answer preserves the same decision mechanism under a changed domain?",
                evidence_hint=f"Based on {card.id}: {card.title}",
            )
        )
    if items:
        return items
    for index, hypothesis in enumerate(hypotheses[:5], 1):
        items.append(
            MiniBlindTestItem(
                id=f"T{index}",
                dimension=hypothesis.dimension,
                scenario=_scenario_for(hypothesis),
                what_to_compare=_compare_prompt_for(hypothesis),
                evidence_hint=f"Fallback from {hypothesis.id}: {hypothesis.hypothesis}",
            )
        )
    return items


def _build_feedback_routes(
    construct_cards: list[ConstructCard],
    hypotheses: list[SoulLiteHypothesis],
) -> list[str]:
    routes = [
        "If wording feels wrong, route to VOICE and collect exact words the user would send.",
        "If a value feels wrong, route to SOUL and collect a counterexample plus the tradeoff that changed the decision.",
        "If a refusal feels wrong, route to BOUNDARIES and collect the exception rule, not just the refusal.",
        "If the answer is plausible but generic, route to the strongest related dimension and ask for a pressure case.",
    ]
    for category in sorted({route for card in construct_cards for route in card.feedback_routes}):
        routes.append(f"Construct-card missing evidence route: {category}.")
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
    evidence = _strip_hypothesis_prefix(hypothesis.hypothesis)
    scenarios = {
        Dimension.SOUL: _soul_scenario(evidence),
        Dimension.BOUNDARIES: (
            "A trusted person asks for an urgent exception that conflicts with "
            f"`{evidence}`. Write the refusal, compromise, or exception rule."
        ),
        Dimension.VOICE: (
            "You need to send a short LINE message in a tense situation where "
            f"`{evidence}` matters. Write the exact message."
        ),
        Dimension.SKILL: _skill_scenario(evidence),
        Dimension.PEOPLE: (
            "A partner's reliability is uncertain and you must decide how much trust or "
            f"visibility to give them, given `{evidence}`."
        ),
    }
    return scenarios.get(
        hypothesis.dimension,
        f"A realistic situation tests whether `{evidence}` changes what you would say or choose.",
    )


def _soul_scenario(evidence: str) -> str:
    if _contains_any(evidence, ("陷害", "人性", "目的")):
        return (
            "A teammate may have undermined you, but the motive is unclear. Decide whether "
            f"to keep investigating, confront them, or move on, given `{evidence}`."
        )
    if _contains_any(evidence, ("收入", "工作本質", "意義", "職業")):
        return (
            "A higher-paying opportunity appears, but it changes the nature of your work. "
            f"Write how `{evidence}` affects the decision."
        )
    if _contains_any(evidence, ("電腦", "職業路徑", "可能性")):
        return (
            "Someone suggests a serious non-computer career path. Write your first reaction "
            f"and decision criteria, given `{evidence}`."
        )
    return (
        "A collaborator asks you to choose between preserving harmony and acting on "
        f"`{evidence}`. Write what you would decide and what you would say."
    )


def _skill_scenario(evidence: str) -> str:
    if _contains_any(
        evidence,
        ("鐵三角", "時程", "範疇", "預算", "不合理", "triangle", "budget", "scope", "schedule"),
    ):
        return (
            "A client wants the same scope and deadline after cutting budget. Use "
            f"`{evidence}` to decide what to push back on and how to explain it."
        )
    if _contains_any(evidence, ("交接班", "交接", "投入", "handoff", "commitment")):
        return (
            "A handoff is vague before a critical shift, and the person says they are already "
            f"done. Use `{evidence}` to decide whether to accept it or intervene."
        )
    if _contains_any(evidence, ("情感勒索", "議價", "報價", "blackmail", "pricing", "negotiation")):
        return (
            "A buyer frames a discount request as friendship, loyalty, or helping them out. "
            f"Use `{evidence}` to decide your pricing response."
        )
    return (
        "A project is behind schedule and the first plan is failing. Use "
        f"`{evidence}` to decide the next action and explain it to the team."
    )


def _compare_prompt_for(hypothesis: SoulLiteHypothesis) -> str:
    prompts = {
        Dimension.SOUL: "Which answer makes the same tradeoff under pressure?",
        Dimension.BOUNDARIES: "Which answer has the more accurate refusal or exception boundary?",
        Dimension.VOICE: "Which answer uses the human's actual wording, register, and length?",
        Dimension.SKILL: "Which answer chooses the more realistic next operating move?",
        Dimension.PEOPLE: "Which answer calibrates trust, risk, and responsibility more like the human?",
    }
    return prompts.get(
        hypothesis.dimension,
        "Which answer reveals a more specific decision pattern instead of generic good judgment?",
    )


def _counterexample_signal(hypothesis: SoulLiteHypothesis) -> str:
    core = _strip_hypothesis_prefix(hypothesis.hypothesis)
    return f"Ask for one time `{core}` was not true."


def _pressure_signal(hypothesis: SoulLiteHypothesis) -> str:
    if hypothesis.dimension == Dimension.VOICE:
        return "Ask how the wording changes when angry, rushed, or speaking to a senior person."
    if hypothesis.dimension == Dimension.PEOPLE:
        return "Ask what happens when trust conflicts with delivery risk."
    return "Ask what happens when time, money, status, or relationship pressure is high."


def _exception_signal(hypothesis: SoulLiteHypothesis) -> str:
    if hypothesis.dimension == Dimension.BOUNDARIES:
        return "Ask the exact condition that would make an exception acceptable."
    if hypothesis.dimension == Dimension.SOUL:
        return "Ask which higher value can override this value."
    return "Ask when this pattern should be suspended."


def _exact_wording_signal(hypothesis: SoulLiteHypothesis) -> str:
    if hypothesis.dimension == Dimension.VOICE:
        return "Collect the exact LINE / email sentence the user would send."
    return "Ask the user to rewrite the persona answer in their own words."


def _decision_tradeoff_signal(hypothesis: SoulLiteHypothesis) -> str:
    if hypothesis.dimension == Dimension.SKILL:
        return "Ask what they would sacrifice first: speed, quality, scope, or relationship."
    if hypothesis.dimension == Dimension.PEOPLE:
        return "Ask what evidence makes them increase or reduce trust."
    if hypothesis.dimension == Dimension.BOUNDARIES:
        return "Ask what they would protect even if the opportunity is attractive."
    return "Ask what they chose against, not only what they chose for."


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


def _card_source_text(hypothesis: SoulLiteHypothesis) -> str:
    evidence_text = " ".join(evidence.content for evidence in hypothesis.evidence)
    return f"{hypothesis.hypothesis} {evidence_text}"


def _source_anchor_ids(evidence_items: list[EvidenceItem]) -> list[int]:
    return sorted({anchor_id for evidence in evidence_items for anchor_id in evidence.source_anchor_ids})


def _source_turn_ids(evidence_items: list[EvidenceItem]) -> list[int]:
    return sorted({turn_id for evidence in evidence_items for turn_id in evidence.source_turn_ids})


def _source_question_ids(evidence_items: list[EvidenceItem]) -> list[str]:
    return sorted({question_id for evidence in evidence_items for question_id in evidence.source_question_ids})


def _policy_status(
    evidence_items: list[EvidenceItem],
) -> Literal["espoused_only", "behavior_supported", "contradicted", "validated"]:
    if any(evidence.layer == Layer.FACT for evidence in evidence_items):
        return "behavior_supported"
    return "espoused_only"


def _max_raw_wrapper_overlap(card: ConstructCard) -> float:
    if not card.supporting_evidence:
        return 0.0
    return max(
        _lexical_ngram_overlap(card.decision_rule, evidence.content)
        for evidence in card.supporting_evidence
    )


def _lexical_ngram_overlap(candidate: str, source: str) -> float:
    candidate_ngrams = _content_ngrams(candidate)
    if not candidate_ngrams:
        return 0.0
    source_ngrams = _content_ngrams(source)
    return len(candidate_ngrams & source_ngrams) / len(candidate_ngrams)


def _content_ngrams(text: str) -> set[str]:
    tokens = [
        token
        for token in _tokenize_for_overlap(text)
        if token not in _STOP_WORDS and len(token) > 1
    ]
    ngrams = set(tokens)
    ngrams.update(" ".join(tokens[index : index + 2]) for index in range(len(tokens) - 1))
    return ngrams


def _tokenize_for_overlap(text: str) -> list[str]:
    normalized = text.lower()
    tokens: list[str] = []
    current: list[str] = []
    for char in normalized:
        if char.isalnum() or "\u4e00" <= char <= "\u9fff":
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _card_route(routes: set[str], category: str) -> str:
    if category in routes:
        return f"Collect {category.replace('_', ' ')} evidence."
    return "not primary route"


def _has_decision_signal(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in DECISION_KEYWORDS)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


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
