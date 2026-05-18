from types import SimpleNamespace

from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.interview.bot import _handle_non_answer, _pause_current_question
from virtualme.storage.db import Dimension, Question, Session


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    async def create(self, **kwargs):
        text = kwargs["messages"][0]["content"].split("Ask this next: ", 1)[1]
        return type("Response", (), {"content": [_Content(text)]})


class _Claude:
    def __init__(self):
        self.messages = _Messages()


class _DB:
    def __init__(self, count: int):
        self.count = count

    async def record_question_non_answer(
        self, interviewee_id: str, question_id: str, week: int
    ) -> int:
        return self.count

    async def load_anchors_summary(self, interviewee_id: str):
        return {}

    async def compute_coverage_gap(self, interviewee_id: str):
        return {}


async def test_handle_non_answer_first_evasion_returns_gentle_bridge():
    question = Question(
        id="Q1",
        week=1,
        dimension=Dimension.STATE,
        text="請說說您最近的工作狀況。",
    )

    reply = await _handle_non_answer(
        "u1",
        "不要問這個",
        question,
        Session(id=1, interviewee_id="u1", week=1),
        SimpleNamespace(select_next=lambda *args, **kwargs: None),
        Settings(anthropic_api_key=SecretStr("test"), use_ppa=False),
        _Claude(),
        _DB(count=1),
        is_meta=False,
        anchors_by_dimension={},
        asked_question_ids=set(),
    )

    assert "這題如果不好說" in reply
    assert "請說說您最近的工作狀況。" in reply


async def test_handle_non_answer_second_evasion_pauses():
    question = Question(
        id="Q1",
        week=1,
        dimension=Dimension.STATE,
        text="請說說您最近的工作狀況。",
    )

    reply = await _handle_non_answer(
        "u1",
        "還是不想答",
        question,
        Session(id=1, interviewee_id="u1", week=1),
        SimpleNamespace(select_next=lambda *args, **kwargs: None),
        Settings(anthropic_api_key=SecretStr("test"), use_ppa=False),
        _Claude(),
        _DB(count=2),
        is_meta=False,
        anchors_by_dimension={},
        asked_question_ids=set(),
    )

    assert reply == _pause_current_question()
