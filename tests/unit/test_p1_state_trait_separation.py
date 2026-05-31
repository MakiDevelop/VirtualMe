"""P1 State-Trait Separation hard gate - Constitution v1.1 §P1."""

import pytest

from virtualme.export.markdown import export_markdown
from virtualme.snapshot.stability_gate import (
    CORE_TRUTH_DIMENSIONS,
    filter_core_truth_candidates,
    is_eligible_for_core_truths,
)
from virtualme.storage.db import DB, Anchor, Dimension, Layer


class TestStabilityGate:
    def test_state_dimension_not_in_core_truth_dimensions(self):
        assert Dimension.STATE not in CORE_TRUTH_DIMENSIONS

    def test_soul_voice_skill_boundaries_in_core_truth_dimensions(self):
        for dimension in [
            Dimension.SOUL,
            Dimension.VOICE,
            Dimension.SKILL,
            Dimension.BOUNDARIES,
        ]:
            assert dimension in CORE_TRUTH_DIMENSIONS

    def test_is_eligible_for_state_anchor_returns_false(self, sample_state_anchor):
        assert is_eligible_for_core_truths(sample_state_anchor) is False

    def test_is_eligible_for_soul_anchor_returns_true(self, sample_soul_anchor):
        assert is_eligible_for_core_truths(sample_soul_anchor) is True

    def test_filter_drops_state_anchors(self, sample_state_anchor, sample_soul_anchor):
        result = filter_core_truth_candidates([sample_state_anchor, sample_soul_anchor])

        assert sample_state_anchor not in result
        assert sample_soul_anchor in result


async def test_state_anchor_not_in_soul_md_core_truths(tmp_path):
    """STATE source anchors must not render as SOUL.md stable patterns."""
    db = await _new_db(tmp_path)
    week_1 = await db.get_or_create_session("u1", week=1)
    week_2 = await db.get_or_create_session("u1", week=2)
    soul_turn_1 = await db.save_turn(week_1.id, "user", "truth matters")
    soul_turn_2 = await db.save_turn(week_2.id, "user", "truth still matters")
    await db.save_anchor(
        "u1",
        Dimension.STATE,
        Layer.PRINCIPLE,
        "最近很累",
        [1, 2, 3],
        ["Q1", "Q2", "Q3"],
    )
    await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "values direct truth under delivery pressure",
        [soul_turn_1.id, soul_turn_2.id],
        ["Q4", "Q5", "Q6"],
    )

    await export_markdown(db, "u1", tmp_path / "exports")
    soul_text = (tmp_path / "exports" / "u1" / "SOUL.md").read_text(encoding="utf-8")
    stable_patterns = _section(
        soul_text,
        "## Validated Patterns",
        "## Recurring but Unvalidated Patterns",
    )

    assert "values direct truth under delivery pressure" in stable_patterns
    assert "最近很累" not in stable_patterns


async def test_state_dimension_still_exported(tmp_path):
    """STATE.md should still be exported as the current-state snapshot."""
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.STATE,
        Layer.PRINCIPLE,
        "最近很累",
        [1, 2, 3],
        ["Q1", "Q2", "Q3"],
    )

    paths = await export_markdown(db, "u1", tmp_path / "exports")
    state_path = tmp_path / "exports" / "u1" / "STATE.md"

    assert "STATE.md" in {path.name for path in paths}
    assert state_path.exists()
    assert "最近很累" in state_path.read_text(encoding="utf-8")


@pytest.fixture
def sample_state_anchor():
    return Anchor(
        interviewee_id="u1",
        dimension=Dimension.STATE,
        layer=Layer.FACT,
        content="最近很累",
        source_turn_ids=[1],
        source_question_ids=["Q1"],
    )


@pytest.fixture
def sample_soul_anchor():
    return Anchor(
        interviewee_id="u1",
        dimension=Dimension.SOUL,
        layer=Layer.PRINCIPLE,
        content="values direct truth under delivery pressure",
        triangulated=True,
        source_turn_ids=[2, 3, 4],
        source_question_ids=["Q2", "Q3", "Q4"],
    )


async def _new_db(tmp_path) -> DB:
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    return db


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]
