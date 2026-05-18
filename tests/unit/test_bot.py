from types import SimpleNamespace

from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.interview import bot
from virtualme.interview.bot import (
    _final_reply,
    _handle_light_greeting,
    _handle_non_answer,
    _is_control_message,
    _pause_current_question,
    _resolve_current_question,
    process_turn,
)
from virtualme.interview.briefing import INTERVIEW_PURPOSE, InterviewBriefing
from virtualme.interview.depth_evaluator import TurnAssessment, TurnKind
from virtualme.storage.db import DB, Dimension, Layer, Question, Session


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
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


class _GreetingDB:
    def __init__(self, last_assistant_content: str):
        self.last_assistant_content = last_assistant_content
        self.current_question_id = None
        self.saved_turns = []
        self.redactions = []
        self.recorded_questions = []

    async def save_turn(self, session_id: int, role: str, content: str):
        self.saved_turns.append((session_id, role, content))
        return SimpleNamespace(id=len(self.saved_turns))

    async def save_redactions(self, turn_id: int, redactions: list):
        self.redactions.append((turn_id, redactions))

    async def get_current_question_id(self, session_id: int):
        return self.current_question_id

    async def set_current_question_id(self, session_id: int, question_id: str):
        self.current_question_id = question_id

    async def record_question_asked(self, interviewee_id: str, question_id: str, week: int):
        self.recorded_questions.append((interviewee_id, question_id, week))

    async def load_anchors_summary(self, interviewee_id: str):
        return {}

    async def get_last_assistant_content(self, session_id: int) -> str | None:
        return self.last_assistant_content

    async def compute_coverage_gap(self, interviewee_id: str):
        return {}


def _selector(question: Question):
    return SimpleNamespace(question_pool={question.week: [question]})


def test_is_control_message_detects_control_replies():
    assert _is_control_message(_pause_current_question()) is True
    assert _is_control_message("好，今天先到這裡。我會把這段先整理起來。") is True  # noqa: RUF001
    assert _is_control_message("你最近工作中最卡的一件事是什麼?") is False


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


async def test_handle_light_greeting_falls_back_when_last_assistant_turn_is_pause():
    question = Question(
        id="Q1",
        week=1,
        dimension=Dimension.STATE,
        text="請說說您最近的工作狀況。",
    )
    db = _GreetingDB(last_assistant_content=_pause_current_question())

    reply = await _handle_light_greeting(
        "u1",
        "哈囉",
        Session(id=1, interviewee_id="u1", week=1),
        _Claude(),
        db,
        _selector(question),
    )

    assert "剛才問的是" not in reply
    assert "我們從【近況】開始。" in reply
    assert "請說說您最近的工作狀況。" in reply


async def test_resolve_current_question_uses_pool_question_when_last_assistant_turn_is_pause():
    question = Question(
        id="Q1",
        week=1,
        dimension=Dimension.STATE,
        text="請說說您最近的工作狀況。",
    )
    db = _GreetingDB(last_assistant_content=_pause_current_question())
    db.current_question_id = question.id

    resolved = await _resolve_current_question(db, _selector(question), session_id=1, week=1)

    assert resolved.text == question.text


async def test_final_reply_system_prompt_includes_briefing_when_present():
    question = Question(
        id="Q1",
        week=1,
        dimension=Dimension.STATE,
        text="請說說您最近的工作狀況。",
    )
    claude = _Claude()
    briefing = InterviewBriefing(
        purpose=INTERVIEW_PURPOSE,
        progress="Week 1 of 4.",
        durable_summary="- durable",
        coverage_gaps="- gap",
        recent_transcript="受訪者: 前一輪回答",
    )

    reply = await _final_reply("u1", question, claude, _DB(count=0), briefing)

    system = claude.messages.calls[0]["system"]
    assert reply == question.text
    assert "INTERVIEW PURPOSE:" in system
    assert "WHAT WE KNOW SO FAR:" in system
    assert "Accumulated anchors:" not in system


async def test_process_turn_builds_briefing_once_and_passes_downstream(tmp_path, monkeypatch):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    question = Question(
        id="Q1",
        week=1,
        dimension=Dimension.STATE,
        text="How has work been?",
    )
    selector = SimpleNamespace(
        question_pool={1: [question]},
        select_next=lambda *args, **kwargs: None,
    )
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    briefing = InterviewBriefing(
        purpose=INTERVIEW_PURPOSE,
        progress="Week 1 of 1.",
        durable_summary="No durable signal extracted yet.",
        coverage_gaps="No computed coverage gaps yet.",
        recent_transcript="No recent conversation yet.",
    )
    calls = []

    async def fake_build(db_arg, interviewee_id, session, max_week):
        calls.append(("build", interviewee_id, session.id, max_week))
        return briefing

    async def fake_evaluate_depth(answer, current_question, claude, briefing_arg=None):
        calls.append(("depth", briefing_arg))
        return TurnAssessment(
            kind=TurnKind.SUFFICIENT,
            depth=Layer.PRINCIPLE,
            needs_follow_up=False,
            confidence=0.9,
        )

    async def fake_extract_anchors(turn, current_question, claude, briefing_arg=None):
        calls.append(("anchor", briefing_arg))
        return []

    async def fake_final_reply(interviewee_id, question, claude, db, briefing_arg=None):
        calls.append(("final", briefing_arg))
        return "final question"

    monkeypatch.setattr(bot, "build_interview_briefing", fake_build)
    monkeypatch.setattr(bot, "evaluate_depth", fake_evaluate_depth)
    monkeypatch.setattr(bot, "extract_anchors", fake_extract_anchors)
    monkeypatch.setattr(bot, "_final_reply", fake_final_reply)

    reply = await process_turn("u1", "I value direct evidence.", object(), db, selector, settings)

    assert reply == "final question"
    assert calls[0] == ("build", "u1", 1, 1)
    assert ("depth", briefing) in calls
    assert ("anchor", briefing) in calls
    assert ("final", briefing) in calls
