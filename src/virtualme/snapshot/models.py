from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from virtualme.storage.db import Dimension, Layer

ReviewVerdict = Literal["like_me", "unlike_me", "unsure", "missing_context"]
ReviewEvidenceQuality = Literal["none", "low", "medium", "medium_high", "high"]

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
    source_session_count: int | None = None
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
    schema_version: str = "0.1"
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
    missing_evidence: list[str] = field(default_factory=list)
