"""Tests for triangulation uniqueness fix — issue #3."""
import pytest
from virtualme.storage.db import Anchor, Dimension, Layer
from virtualme.interview.follow_up import _has_triangulated_repeat


class TestHasTriangulatedRepeat:
    """Triangulation requires 3 DIFFERENT questions, not just 3 turns."""

    def test_same_question_multiple_turns_not_triangulated(self):
        """Multiple turns from the same question should NOT count as triangulation."""
        anchor = Anchor(
            interviewee_id="test",
            dimension=Dimension.SOUL,
            layer=Layer.PRINCIPLE,
            content="honesty is the best policy",
            triangulated=False,
            source_turn_ids=[1, 2, 3, 4, 5],
            source_question_ids=["Q1", "Q1", "Q1", "Q1", "Q1"],
        )
        answer = "honesty is the best policy and honesty matters most"
        assert _has_triangulated_repeat(answer, [anchor]) is False

    def test_three_different_questions_is_triangulated(self):
        """Three turns from three different questions SHOULD trigger triangulation."""
        anchor = Anchor(
            interviewee_id="test",
            dimension=Dimension.SOUL,
            layer=Layer.PRINCIPLE,
            content="honesty is the best policy",
            triangulated=False,
            source_turn_ids=[1, 2, 3],
            source_question_ids=["Q1", "Q2", "Q3"],
        )
        answer = "honesty is the best policy and honesty matters most"
        assert _has_triangulated_repeat(answer, [anchor]) is True

    def test_two_different_questions_not_triangulated(self):
        """Only two different questions should NOT trigger triangulation."""
        anchor = Anchor(
            interviewee_id="test",
            dimension=Dimension.SOUL,
            layer=Layer.PRINCIPLE,
            content="honesty is the best policy",
            triangulated=False,
            source_turn_ids=[1, 2, 3, 4, 5],
            source_question_ids=["Q1", "Q1", "Q2", "Q2", "Q2"],
        )
        answer = "honesty is the best policy and honesty matters most"
        assert _has_triangulated_repeat(answer, [anchor]) is False

    def test_fact_layer_ignored(self):
        """FACT layer anchors should never trigger triangulation."""
        anchor = Anchor(
            interviewee_id="test",
            dimension=Dimension.SOUL,
            layer=Layer.FACT,
            content="honesty is the best policy",
            triangulated=False,
            source_turn_ids=[1, 2, 3],
            source_question_ids=["Q1", "Q2", "Q3"],
        )
        answer = "honesty is the best policy and honesty matters most"
        assert _has_triangulated_repeat(answer, [anchor]) is False

    def test_low_word_overlap_ignored(self):
        """Low word overlap should not trigger even with 3+ different questions."""
        anchor = Anchor(
            interviewee_id="test",
            dimension=Dimension.SOUL,
            layer=Layer.PRINCIPLE,
            content="honesty is the best policy",
            triangulated=False,
            source_turn_ids=[1, 2, 3],
            source_question_ids=["Q1", "Q2", "Q3"],
        )
        answer = "maybe sometimes perhaps"
        assert _has_triangulated_repeat(answer, [anchor]) is False

    def test_empty_source_question_ids_falls_back_to_empty(self):
        """Anchors with empty source_question_ids should not crash."""
        anchor = Anchor(
            interviewee_id="test",
            dimension=Dimension.SOUL,
            layer=Layer.PRINCIPLE,
            content="honesty is the best policy",
            triangulated=False,
            source_turn_ids=[1, 2, 3],
            source_question_ids=[],
        )
        answer = "honesty is the best policy and honesty matters most"
        # Empty question IDs = 0 unique questions < 3 threshold
        assert _has_triangulated_repeat(answer, [anchor]) is False
