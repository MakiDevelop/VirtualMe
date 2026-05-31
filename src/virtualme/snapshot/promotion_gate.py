from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from virtualme.storage.db import Anchor


class PromotionTier(StrEnum):
    OBSERVED = "observed"
    RECURRING = "recurring"
    CROSS_SESSION = "cross_session"
    VALIDATED = "validated"


class PromotionDecision(BaseModel):
    tier: PromotionTier
    can_render_core_truth: bool
    can_claim_validated: bool
    requires_hedging: bool
    reason: str
    missing_evidence: list[str] = Field(default_factory=list)


def classify_anchor(
    anchor: Anchor,
    *,
    source_session_count: int | None = None,
    human_validated: bool = False,
) -> PromotionDecision:
    """Classify anchor maturity without treating triangulation as validation."""
    session_count = source_session_count or 0
    if human_validated and session_count >= 2:
        return PromotionDecision(
            tier=PromotionTier.VALIDATED,
            can_render_core_truth=True,
            can_claim_validated=True,
            requires_hedging=False,
            reason="cross-session evidence plus human validation",
        )
    if session_count >= 2:
        return PromotionDecision(
            tier=PromotionTier.CROSS_SESSION,
            can_render_core_truth=True,
            can_claim_validated=False,
            requires_hedging=True,
            reason="evidence spans multiple sessions but is not human-validated",
            missing_evidence=["human_validation"],
        )
    if anchor.triangulated:
        return PromotionDecision(
            tier=PromotionTier.RECURRING,
            can_render_core_truth=False,
            can_claim_validated=False,
            requires_hedging=True,
            reason="recurring across questions, but not cross-session validated",
            missing_evidence=["cross_session_evidence", "human_validation"],
        )
    return PromotionDecision(
        tier=PromotionTier.OBSERVED,
        can_render_core_truth=False,
        can_claim_validated=False,
        requires_hedging=True,
        reason="single observation or weak evidence",
        missing_evidence=["repeated_question_evidence", "cross_session_evidence"],
    )
