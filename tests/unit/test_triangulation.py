"""Tests for triangulation uniqueness fix — issue #3."""

from virtualme.interview.follow_up import _has_triangulated_repeat
from virtualme.storage.db import DB, Anchor, Dimension, Layer


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


async def test_save_anchor_merges_similar_principles_and_marks_triangulated(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    first = await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "directness over deference",
        [1],
        ["Q1"],
    )
    second = await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "directness matters more than deference",
        [2],
        ["Q2"],
    )
    third = await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "I choose directness over deference",
        [3],
        ["Q3"],
    )

    assert first.id == second.id == third.id
    assert third.triangulated is True
    assert third.source_turn_ids == [1, 2, 3]
    assert third.source_question_ids == ["Q1", "Q2", "Q3"]

    summary = await db.load_anchors_summary("u1")
    assert len(summary[Dimension.SOUL]) == 1
    assert summary[Dimension.SOUL][0].triangulated is True

    principles = await db.load_triangulated("u1")
    assert len(principles) == 1
    assert principles[0].source_turn_ids == [1, 2, 3]


async def test_same_question_repeats_merge_but_do_not_triangulate(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    for turn_id in [1, 2, 3]:
        anchor = await db.save_anchor(
            "u1",
            Dimension.SOUL,
            Layer.PRINCIPLE,
            "honesty matters more than polish",
            [turn_id],
            ["Q1"],
        )

    assert anchor.triangulated is False
    assert anchor.source_turn_ids == [1, 2, 3]
    assert anchor.source_question_ids == ["Q1"]
    assert await db.load_triangulated("u1") == []


async def test_non_principle_anchors_are_not_merged(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    first = await db.save_anchor(
        "u1",
        Dimension.HISTORY,
        Layer.FACT,
        "joined the profession in 2018",
        [1],
        ["Q1"],
    )
    second = await db.save_anchor(
        "u1",
        Dimension.HISTORY,
        Layer.FACT,
        "joined the profession in 2018",
        [2],
        ["Q2"],
    )

    assert first.id != second.id
    summary = await db.load_anchors_summary("u1")
    assert len(summary[Dimension.HISTORY]) == 2
