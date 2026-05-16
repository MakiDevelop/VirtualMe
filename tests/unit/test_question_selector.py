import pytest

from virtualme.interview.question_selector import (
    QuestionSelector,
    default_question_pool_path,
    load_question_pool,
)
from virtualme.storage.db import Anchor, Dimension, Layer, Question, Session


def _question(id_: str, dimension: Dimension, energy_tax: str = "mid") -> Question:
    return Question(id=id_, week=1, dimension=dimension, text=id_, energy_tax=energy_tax)


def _session() -> Session:
    return Session(id=1, interviewee_id="u1", week=1)


def test_returns_none_when_unexplored_layer_exists():
    selector = QuestionSelector({1: [_question("H1", Dimension.HISTORY)]})
    anchors = {
        Dimension.HISTORY: [
            Anchor(
                interviewee_id="u1",
                dimension=Dimension.HISTORY,
                layer=Layer.FACT,
                content="joined once",
            )
        ]
    }
    assert selector.select_next(_session(), None, anchors, energy=5) is None


def test_picks_biggest_gap_dimension():
    selector = QuestionSelector(
        {1: [_question("H1", Dimension.HISTORY), _question("S1", Dimension.SKILL)]}
    )
    anchors = {
        Dimension.HISTORY: [
            Anchor(
                interviewee_id="u1",
                dimension=Dimension.HISTORY,
                layer=Layer.PRINCIPLE,
                content="history principle",
            )
        ]
    }
    assert selector.select_next(_session(), None, anchors, energy=5).dimension == Dimension.SKILL


def test_prefers_unasked_question_in_target_dimension():
    selector = QuestionSelector(
        {
            1: [
                _question("S1", Dimension.SKILL),
                _question("S2", Dimension.SKILL),
                _question("H1", Dimension.HISTORY),
            ]
        }
    )
    anchors = {
        Dimension.HISTORY: [
            Anchor(
                interviewee_id="u1",
                dimension=Dimension.HISTORY,
                layer=Layer.PRINCIPLE,
                content="history principle",
            )
        ]
    }

    selected = selector.select_next(
        _session(),
        None,
        anchors,
        energy=5,
        asked_question_ids={"S1"},
    )

    assert selected.id == "S2"


def test_target_dimension_falls_back_when_all_matching_questions_were_asked():
    selector = QuestionSelector(
        {
            1: [
                _question("S1", Dimension.SKILL),
                _question("S2", Dimension.SKILL),
                _question("H1", Dimension.HISTORY),
            ]
        }
    )
    anchors = {
        Dimension.HISTORY: [
            Anchor(
                interviewee_id="u1",
                dimension=Dimension.HISTORY,
                layer=Layer.PRINCIPLE,
                content="history principle",
            )
        ]
    }

    selected = selector.select_next(
        _session(),
        None,
        anchors,
        energy=5,
        asked_question_ids={"S1", "S2"},
    )

    assert selected.id == "S1"


def test_low_energy_switches_to_light_topic():
    selector = QuestionSelector(
        {
            1: [
                _question("H1", Dimension.HISTORY, "high"),
                _question("STATE1", Dimension.STATE, "low"),
            ]
        }
    )
    assert selector.select_next(_session(), None, {}, energy=2).dimension == Dimension.STATE


def test_load_packaged_question_pool_uses_current_yaml_shape():
    pool = load_question_pool()

    assert default_question_pool_path().name == "question-pool.yaml"
    assert 1 in pool
    assert pool[1][0].id == "H1"
    assert pool[1][0].dimension == Dimension.HISTORY


def test_load_question_pool_supports_legacy_root_list(tmp_path):
    path = tmp_path / "questions.yaml"
    path.write_text(
        """
        - id: Q1
          week: 1
          dimension: STATE
          text: How are you?
        """,
        encoding="utf-8",
    )

    pool = load_question_pool(path)

    assert pool[1][0].id == "Q1"


def test_load_question_pool_rejects_invalid_shape(tmp_path):
    path = tmp_path / "questions.yaml"
    path.write_text("version: 1\nquestions: nope\n", encoding="utf-8")

    with pytest.raises(ValueError, match="questions list"):
        load_question_pool(path)
