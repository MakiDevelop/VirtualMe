"""P5 Self-Correction & Agency hard gate — Constitution v1.1 §P5."""

from __future__ import annotations

from typing import get_args

from virtualme.snapshot.core import (
    ConstructCard,
    ConstructCardReview,
    EvidenceItem,
    ReviewVerdict,
    SnapshotBundle,
    apply_construct_card_reviews,
)
from virtualme.snapshot.hedge_validator import (
    find_unhedged_assertions,
    has_hedge_marker,
)
from virtualme.storage.db import Dimension, Layer


class TestHedgeValidator:
    def test_rejects_unhedged_english_assertion(self):
        text = "You are an introvert."
        violations = find_unhedged_assertions(text)
        assert len(violations) == 1
        assert "You are" in violations[0].matched_text

    def test_rejects_unhedged_chinese_assertion(self):
        text = "你是內向的人。"
        violations = find_unhedged_assertions(text)
        assert len(violations) >= 1

    def test_rejects_essentialist_phrasing(self):
        text = "Your true self is risk-averse."
        violations = find_unhedged_assertions(text)
        assert len(violations) >= 1

    def test_accepts_hedged_phrasing_chinese(self):
        text = "目前觀察到你在 W2-W5 多次提到風險意識。"
        violations = find_unhedged_assertions(text)
        assert violations == []
        assert has_hedge_marker(text)

    def test_accepts_hedged_phrasing_english(self):
        text = "Tentative observation: you tend to favor caution in financial decisions (W2)."
        violations = find_unhedged_assertions(text)
        assert violations == []
        assert has_hedge_marker(text)

    def test_multiline_violation_tracking(self):
        text = "First line: hedged 目前觀察到 X.\nSecond line: You are bold."
        violations = find_unhedged_assertions(text)
        assert len(violations) == 1
        assert violations[0].line_number == 2


def _reviewed_card(verdict: str) -> ConstructCard:
    evidence = EvidenceItem(
        kind="anchor",
        dimension=Dimension.SOUL,
        layer=Layer.PRINCIPLE,
        content="chooses careful tradeoffs under pressure",
        source_anchor_ids=[1, 2],
        source_turn_ids=[10, 11],
        source_question_ids=["Q1", "Q2"],
        confidence=0.9,
    )
    card = ConstructCard(
        id="C1",
        title="Careful Tradeoffs",
        decision_rule="protect downside risk by choosing reversible options",
        trigger_context="high-uncertainty decisions",
        protected_value="downside risk",
        traded_value="speed",
        default_action="choose reversible options",
        refused_action="commit before evidence appears",
        exception_rule="can move faster when rollback is cheap",
        register=None,
        falsifier="Would repeatedly choose irreversible speed over risk control.",
        supporting_evidence=[evidence],
        disconfirming_evidence=[],
        source_anchor_ids=[1, 2],
        source_turn_ids=[10, 11],
        source_question_ids=["Q1", "Q2"],
        dimension_tags=[Dimension.SOUL],
        confidence_level="validated",
        confidence_reason="multi-session behavioral support",
        confidence_checks={"multi_anchor_support": True, "human_reviewed": False},
        missing_evidence=[],
        blind_test_probe=None,
        feedback_routes=["review C1"],
        extraction_method="rule_based",
        policy_status="validated",
        stability_scope="multi-session",
        context_dependence="under pressure",
        exception_archetype=None,
    )
    review = ConstructCardReview(
        card_id="C1",
        verdict=verdict,
        reviewer="Maki",
        notes="This does not match me.",
        counterexample_note="I often choose speed in this context.",
        evidence_quality="high",
    )
    bundle = SnapshotBundle(
        interviewee_id="u1",
        generated_at="2026-05-20T00:00:00+00:00",
        construct_cards=[card],
        hypotheses=[],
        mini_blind_test=[],
        feedback_routes=[],
    )
    return apply_construct_card_reviews(bundle, [review]).construct_cards[0]


def test_unlike_me_review_sets_confidence_insufficient():
    """P5: unlike_me blocks promotion even after prior validated status."""
    card = _reviewed_card("unlike_me")
    assert card.confidence_level == "insufficient"
    assert card.confidence_checks["human_confirmed"] is False
    assert card.disconfirming_evidence[-1].kind == "human_review"


def test_unlike_me_review_sets_policy_contradicted():
    """P5: unlike_me review sets policy_status to contradicted."""
    card = _reviewed_card("unlike_me")
    assert card.policy_status == "contradicted"


def test_restart_commands_present():
    """Smoke test: restart_interview / restart_dimension entrypoints still exist."""
    from virtualme.interview import commands
    from virtualme.storage.db import DB

    assert hasattr(DB, "restart_interview")
    assert hasattr(DB, "restart_dimension")
    assert hasattr(commands, "format_restart_reply")


def test_construct_card_review_verdicts_exist():
    """Smoke test: ReviewVerdict keeps all review states."""
    verdicts = set(get_args(ReviewVerdict))
    assert {"like_me", "unlike_me", "unsure", "missing_context"} <= verdicts
