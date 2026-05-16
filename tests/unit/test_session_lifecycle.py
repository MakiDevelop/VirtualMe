from virtualme.interview import session_lifecycle
from virtualme.interview.session_lifecycle import (
    finalize_session_if_closing,
    is_persona_sufficient,
    is_session_closing,
    is_session_stale,
)
from virtualme.interview.triples import PersonaTriple
from virtualme.storage.db import Dimension, Turn


def test_is_session_closing_true():
    assert is_session_closing("好累了,今天先這樣")


def test_is_session_closing_false():
    assert not is_session_closing("我覺得")


def test_closing_phrase_in_non_closing_context_does_not_close():
    assert not is_session_closing("bye is what I never say")


def test_is_session_closing_without_bot_echo():
    assert is_session_closing("bye")
    assert is_session_closing("今天先這樣了")


def test_closing_phrase_in_long_context_does_not_close():
    assert not is_session_closing("I was tired of the old workflow so I rebuilt it")


def test_is_session_stale_true_for_old_turn():
    from datetime import UTC, datetime, timedelta

    assert is_session_stale(datetime.now(UTC) - timedelta(minutes=31))


def test_is_persona_sufficient_true_at_round_cap():
    assert is_persona_sufficient(3, 3, {}) is True


def test_is_persona_sufficient_true_with_voice_and_boundaries_anchors():
    anchors = {
        Dimension.VOICE: [object(), object(), object()],
        Dimension.BOUNDARIES: [object(), object(), object()],
    }

    assert is_persona_sufficient(2, 3, anchors) is True


def test_is_persona_sufficient_false_when_round_and_anchors_are_insufficient():
    anchors = {
        Dimension.VOICE: [object(), object()],
        Dimension.BOUNDARIES: [object(), object(), object()],
    }

    assert is_persona_sufficient(2, 3, anchors) is False


async def test_finalize_session_if_closing_extracts_and_saves(monkeypatch):
    saved = []
    completed = []

    async def fake_extract(session_id, turns, claude):
        return [
            PersonaTriple(
                subject="interviewee",
                relation="preference",
                object="direct questions",
                source_turn_ids=[1],
            )
        ]

    class FakeDB:
        async def save_triple(self, triple):
            saved.append(triple)

        async def mark_session_completed(self, session_id):
            completed.append(session_id)

    monkeypatch.setattr(session_lifecycle, "extract_triples_from_session", fake_extract)
    turns = [Turn(id=1, session_id=7, role="user", content="done", content_hash="h")]
    count = await finalize_session_if_closing(
        7,
        "u1",
        "i'm done",
        turns,
        object(),
        FakeDB(),
    )
    assert count == 1
    assert saved[0].interviewee_id == "u1"
    assert completed == [7]


async def test_finalize_session_if_closing_normal_turn_returns_zero(monkeypatch):
    called = False

    async def fake_extract(session_id, turns, claude):
        nonlocal called
        called = True
        return []

    class FakeDB:
        async def save_triple(self, triple):
            raise AssertionError("should not save")

        async def mark_session_completed(self, session_id):
            raise AssertionError("should not complete")

    monkeypatch.setattr(session_lifecycle, "extract_triples_from_session", fake_extract)
    count = await finalize_session_if_closing(7, "u1", "normal", [], object(), FakeDB())
    assert count == 0
    assert not called
