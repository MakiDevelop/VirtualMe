"""Contract tests for the always-on, pre-LLM crisis gate."""

from __future__ import annotations

import hashlib
import inspect
import json
import re

import aiosqlite
import pytest
from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.interview import crisis
from virtualme.interview.bot import CrisisReply, process_turn
from virtualme.interview.crisis import (
    CRISIS_LOCKED_REPLY,
    CRISIS_PATTERNS,
    CRISIS_REPLY,
    CRISIS_RESUMED_REPLY,
    CrisisCategory,
    detect_crisis,
)
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB, Dimension, Question
from virtualme.transport import line

CRISIS_CASES = (
    (CrisisCategory.SELF_HARM, "我最近一直想死"),
    (CrisisCategory.SELF_HARM, "我不想活了"),
    (CrisisCategory.SELF_HARM, "我想了結自己"),
    (CrisisCategory.SELF_HARM, "I want to die"),
    (CrisisCategory.SELF_HARM, "I might kill myself"),
    (CrisisCategory.HARM_OTHERS, "我想殺了他"),
    (CrisisCategory.HARM_OTHERS, "我想傷害某人"),
    (CrisisCategory.HARM_OTHERS, "我要殺人"),
    (CrisisCategory.HARM_OTHERS, "I want to hurt someone"),
    (CrisisCategory.HARM_OTHERS, "I might kill him"),
    (CrisisCategory.PANIC_DISSOCIATION, "我正在恐慌發作"),
    (CrisisCategory.PANIC_DISSOCIATION, "我現在喘不過氣"),
    (CrisisCategory.PANIC_DISSOCIATION, "我好像在解離"),
    (CrisisCategory.PANIC_DISSOCIATION, "I'm having a panic attack"),
    (CrisisCategory.PANIC_DISSOCIATION, "I feel like I'm dissociating"),
    (CrisisCategory.CANNOT_CONTINUE, "我撐不下去了"),
    (CrisisCategory.CANNOT_CONTINUE, "我不行了"),
    (CrisisCategory.CANNOT_CONTINUE, "我沒辦法繼續"),
    (CrisisCategory.CANNOT_CONTINUE, "I can't keep going"),
    (CrisisCategory.CANNOT_CONTINUE, "I can't go on"),
)

FALSE_POSITIVES = (
    "我很累",
    "工作壓力好大",
    "我不會自殺啦",
    "我沒有想死",
    "我朋友以前說想死",
    "朋友說我想死",
    "這題我不想答",
    "今天先到這",
    "我不想傷害某人",
    "I am not suicidal",
    "I won't kill myself",
    "My friend said I want to die",
    'The phrase "suicide" appears in the article.',
    'The movie character said "kill him".',
)


class _ExplodingMessages:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        raise AssertionError("crisis paths must not call the LLM")


class _ExplodingClient:
    def __init__(self) -> None:
        self.messages = _ExplodingMessages()


class _Content:
    def __init__(self, text: str):
        self.text = text


class _WorkingMessages:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if kwargs["max_tokens"] == 120:
            text = json.dumps(
                {
                    "kind": "SUFFICIENT",
                    "depth": "principle",
                    "needs_follow_up": False,
                    "confidence": 0.9,
                }
            )
        elif kwargs["max_tokens"] in (500, 900):
            text = "[]"
        else:
            text = "Please continue with the next answer."
        return type("Response", (), {"content": [_Content(text)]})


class _WorkingClient:
    def __init__(self) -> None:
        self.messages = _WorkingMessages()


def _selector() -> QuestionSelector:
    question = Question(
        id="Q1",
        week=1,
        dimension=Dimension.STATE,
        text="How has work been?",
    )
    return QuestionSelector({1: [question]})


def _settings(tmp_path, *, consent_required: bool = False) -> Settings:
    return Settings(
        anthropic_api_key=SecretStr("test"),
        byok_enabled=False,
        consent_required=consent_required,
        byok_keys_dir=str(tmp_path / "keys"),
        use_ppa=False,
    )


async def _new_db(tmp_path) -> DB:
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    return db


async def _count(db: DB, table: str) -> int:
    async with aiosqlite.connect(db.path) as conn:
        row = await (await conn.execute(f"SELECT COUNT(*) FROM {table}")).fetchone()
    return int(row[0])


async def _crisis_rows(db: DB) -> list[tuple[str, str, str | None]]:
    async with aiosqlite.connect(db.path) as conn:
        cursor = await conn.execute(
            "SELECT interviewee_id, category, resolved_at FROM crisis_events ORDER BY id"
        )
        return await cursor.fetchall()


@pytest.mark.parametrize(("expected_category", "message"), CRISIS_CASES)
async def test_crisis_fixture_stops_before_turn_storage_and_llm(
    tmp_path,
    expected_category: CrisisCategory,
    message: str,
):
    db = await _new_db(tmp_path)
    client = _ExplodingClient()

    reply = await process_turn(
        "interviewee-1",
        message,
        client,
        db,
        _selector(),
        _settings(tmp_path),
    )

    assert isinstance(reply, CrisisReply)
    assert reply == CRISIS_REPLY
    assert reply.category is expected_category
    assert client.messages.calls == 0
    assert await _count(db, "turns") == 0
    assert await _count(db, "anchors") == 0
    assert await _count(db, "sessions") == 0
    assert await _crisis_rows(db) == [
        ("interviewee-1", expected_category.value, None)
    ]


@pytest.mark.parametrize("message", FALSE_POSITIVES)
def test_false_positive_set_does_not_trigger(message: str):
    assert detect_crisis(message) is None


@pytest.mark.parametrize(
    "message",
    (
        "好想死喔這題",
        "想死XD",
        "笑死我想死欸",
        "解離這個概念我看過",
        "課本說解離",
        "書上寫解離",
    ),
)
def test_context_sensitive_false_positives_do_not_trigger(message: str):
    assert detect_crisis(message) is None


@pytest.mark.parametrize(
    ("message", "expected_category"),
    (
        ("我真的想死", CrisisCategory.SELF_HARM),
        ("我一直想死", CrisisCategory.SELF_HARM),
        ("想死", CrisisCategory.SELF_HARM),
        ("我真的想死喔", CrisisCategory.SELF_HARM),
        ("我每天都想死啦", CrisisCategory.SELF_HARM),
        ("我最近常常解離", CrisisCategory.PANIC_DISSOCIATION),
        ("我感覺自己在解離", CrisisCategory.PANIC_DISSOCIATION),
    ),
)
def test_context_sensitive_crisis_mentions_trigger(
    message: str, expected_category: CrisisCategory
):
    assert detect_crisis(message) is expected_category


def test_each_category_has_at_least_five_patterns_per_language():
    assert set(CRISIS_PATTERNS) == set(CrisisCategory)
    for languages in CRISIS_PATTERNS.values():
        assert len(languages["zh"]) >= 5
        assert len(languages["en"]) >= 5


def test_crisis_detection_has_no_disable_switch_or_environment_access():
    forbidden_tokens = ("enable", "disable", "off", "skip")
    forbidden_fields = [
        field_name
        for field_name in Settings.model_fields
        if "crisis" in field_name.casefold()
        and any(token in field_name.casefold() for token in forbidden_tokens)
    ]
    source = inspect.getsource(crisis)

    assert forbidden_fields == []
    assert "getenv" not in source
    assert "os.environ" not in source
    assert "Settings" not in source


async def test_locked_interview_returns_fixed_reply_without_turn_or_llm(tmp_path):
    db = await _new_db(tmp_path)
    await db.record_crisis_event("interviewee-1", CrisisCategory.SELF_HARM.value)
    client = _ExplodingClient()

    reply = await process_turn(
        "interviewee-1",
        "今天工作還可以",
        client,
        db,
        _selector(),
        _settings(tmp_path),
    )

    assert reply == CRISIS_LOCKED_REPLY
    assert client.messages.calls == 0
    assert await _count(db, "turns") == 0
    assert await _crisis_rows(db) == [
        ("interviewee-1", CrisisCategory.SELF_HARM.value, None)
    ]


@pytest.mark.parametrize(
    "resume_message",
    ("繼續訪談", "  「繼續訪談」。  ", "continue interview", "...Continue Interview!"),
)
async def test_resume_unlocks_without_storing_resume_and_next_turn_runs_normally(
    tmp_path,
    resume_message: str,
):
    db = await _new_db(tmp_path)
    await db.record_crisis_event("interviewee-1", CrisisCategory.CANNOT_CONTINUE.value)
    blocked_client = _ExplodingClient()

    reply = await process_turn(
        "interviewee-1",
        resume_message,
        blocked_client,
        db,
        _selector(),
        _settings(tmp_path),
    )

    assert reply == CRISIS_RESUMED_REPLY
    assert blocked_client.messages.calls == 0
    assert await _count(db, "turns") == 0
    rows = await _crisis_rows(db)
    assert rows[0][:2] == ("interviewee-1", CrisisCategory.CANNOT_CONTINUE.value)
    assert rows[0][2] is not None
    assert not await db.is_crisis_locked("interviewee-1")

    working_client = _WorkingClient()
    normal_reply = await process_turn(
        "interviewee-1",
        "I prefer decisions backed by direct evidence.",
        working_client,
        db,
        _selector(),
        _settings(tmp_path),
    )
    assert normal_reply not in {CRISIS_REPLY, CRISIS_LOCKED_REPLY, CRISIS_RESUMED_REPLY}
    assert working_client.messages.calls > 0
    assert await _count(db, "turns") >= 2


async def test_crisis_precedes_consent_gate(tmp_path):
    db = await _new_db(tmp_path)
    client = _ExplodingClient()
    settings = _settings(tmp_path, consent_required=True)

    reply = await process_turn(
        "interviewee-1",
        "我想死",
        client,
        db,
        _selector(),
        settings,
    )

    assert reply == CRISIS_REPLY
    assert client.messages.calls == 0
    assert not (tmp_path / "keys").exists()
    assert await _count(db, "turns") == 0
    assert await _crisis_rows(db) == [
        ("interviewee-1", CrisisCategory.SELF_HARM.value, None)
    ]


class _TransportDB:
    def __init__(self) -> None:
        self.done: list[str] = []
        self.failed: list[tuple[str, str]] = []

    async def mark_transport_event_done(self, event_id: str) -> None:
        self.done.append(event_id)

    async def mark_transport_event_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


class _FakeApiClient:
    def __init__(self, configuration):
        self.configuration = configuration

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None


async def test_line_crisis_reply_pushes_minimal_content_free_alert(monkeypatch, tmp_path):
    original_message = "secret original message: I want to die"
    sent: list[tuple[str, str, str]] = []
    db = _TransportDB()

    async def fake_process_turn(**kwargs):
        assert kwargs["incoming_message"] == original_message
        return CrisisReply(CRISIS_REPLY, category=CrisisCategory.SELF_HARM)

    class _FakeMessagingApi:
        def __init__(self, _api_client):
            pass

        async def reply_message(self, request):
            sent.append(("reply", request.reply_token, request.messages[0].text))

        async def push_message(self, request):
            sent.append(("push", request.to, request.messages[0].text))

    settings = _settings(tmp_path)
    settings.crisis_alert_line_user_id = "U-ALERT"
    monkeypatch.setattr(line, "process_turn", fake_process_turn)
    monkeypatch.setattr(line, "AsyncApiClient", _FakeApiClient)
    monkeypatch.setattr(line, "AsyncMessagingApi", _FakeMessagingApi)

    await line._process_text_event(
        event_id="event-1",
        reply_token="reply-token",
        interviewee_id="U123",
        incoming_message=original_message,
        access_token="token",
        claude=object(),
        db=db,
        selector=object(),
        settings=settings,
    )

    assert db.done == ["event-1"]
    assert db.failed == []
    assert len(sent) == 2
    alert_kind, alert_target, alert_text = sent[0]
    assert (alert_kind, alert_target) == ("push", "U-ALERT")
    assert alert_text.startswith(
        f"crisis gate triggered {hashlib.sha256(b'U123').hexdigest()[:8]} "
    )
    assert alert_text.endswith(f" {CrisisCategory.SELF_HARM.value}")
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", alert_text)
    assert original_message not in alert_text
    assert sent[1] == ("reply", "reply-token", CRISIS_REPLY)


async def test_line_crisis_alert_failure_does_not_block_interviewee_reply(
    monkeypatch,
    caplog,
):
    sent_replies: list[str] = []
    db = _TransportDB()

    async def fake_process_turn(**_kwargs):
        return CrisisReply(CRISIS_REPLY, category=CrisisCategory.PANIC_DISSOCIATION)

    class _FailingAlertMessagingApi:
        def __init__(self, _api_client):
            pass

        async def reply_message(self, request):
            sent_replies.append(request.messages[0].text)

        async def push_message(self, _request):
            raise RuntimeError("alert unavailable")

    settings = Settings(
        anthropic_api_key=SecretStr("test"),
        crisis_alert_line_user_id="U-ALERT",
    )
    monkeypatch.setattr(line, "process_turn", fake_process_turn)
    monkeypatch.setattr(line, "AsyncApiClient", _FakeApiClient)
    monkeypatch.setattr(line, "AsyncMessagingApi", _FailingAlertMessagingApi)

    await line._process_text_event(
        event_id="event-1",
        reply_token="reply-token",
        interviewee_id="U123",
        incoming_message="我正在恐慌發作",
        access_token="token",
        claude=object(),
        db=db,
        selector=object(),
        settings=settings,
    )

    assert sent_replies == [CRISIS_REPLY]
    assert db.done == ["event-1"]
    assert "Crisis alert push failed" in caplog.text
