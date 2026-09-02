import base64
import hashlib
import hmac
import json

from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.transport import line


class FakeRequest:
    def __init__(self, body: bytes, signature: str):
        self._body = body
        self.headers = {"x-line-signature": signature}

    async def body(self):
        return self._body


class FakeDB:
    def __init__(
        self,
        *,
        has_existing_session: bool = True,
        session_lookup_error: Exception | None = None,
    ):
        self.claimed: set[str] = set()
        self.done: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.has_existing_session = has_existing_session
        self.session_lookup_error = session_lookup_error
        self.session_lookups: list[str] = []

    async def has_any_session(self, interviewee_id: str) -> bool:
        self.session_lookups.append(interviewee_id)
        if self.session_lookup_error is not None:
            raise self.session_lookup_error
        return self.has_existing_session

    async def claim_transport_event(
        self,
        event_id: str,
        platform: str,
        interviewee_id: str | None = None,
        message_id: str | None = None,
    ) -> bool:
        assert platform == "line"
        assert interviewee_id == "U123"
        assert message_id == "m1"
        if event_id in self.claimed:
            return False
        self.claimed.add(event_id)
        return True

    async def mark_transport_event_done(self, event_id: str) -> None:
        self.done.append(event_id)

    async def mark_transport_event_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))

    async def run(self):
        for func, args, kwargs in self.tasks:
            await func(*args, **kwargs)


def _settings() -> Settings:
    return Settings(
        anthropic_api_key=SecretStr("test"),
        line_channel_secret=SecretStr("secret"),
        line_channel_access_token=SecretStr("token"),
    )


def _line_body(reply_token: str | None = "reply-token") -> bytes:
    event = {
        "type": "message",
        "mode": "active",
        "timestamp": 1,
        "webhookEventId": "01FZ74A0TDDPYRVKNK77XKC3ZR",
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "U123"},
        "message": {"id": "m1", "type": "text", "text": "hello", "quoteToken": "quote-token"},
    }
    if reply_token is not None:
        event["replyToken"] = reply_token
    return json.dumps({"destination": "bot", "events": [event]}).encode()


def _signature(body: bytes) -> str:
    digest = hmac.new(b"secret", body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


async def test_invalid_signature_returns_status():
    body = _line_body()
    result = await line.handle_line_webhook(
        FakeRequest(body, "bad"),
        object(),
        object(),
        object(),
        settings=_settings(),
    )
    assert result == {"status": "invalid_signature"}


async def test_missing_credentials_returns_clear_error():
    settings = Settings(anthropic_api_key=SecretStr("test"))
    body = _line_body()
    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        object(),
        object(),
        settings=settings,
    )
    assert result == {"status": "missing_line_credentials"}


async def test_valid_text_event_calls_process_turn_and_reply(monkeypatch):
    body = _line_body()
    sent = []
    background = FakeBackgroundTasks()
    db = FakeDB()

    async def fake_process_turn(**kwargs):
        assert kwargs["interviewee_id"] == "U123"
        assert kwargs["incoming_message"] == "hello"
        return "reply"

    class FakeApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeMessagingApi:
        def __init__(self, api_client):
            self.api_client = api_client

        async def reply_message(self, request):
            sent.append(("reply", request.reply_token, request.messages[0].text))

        async def push_message(self, request):
            sent.append(("push", request.to, request.messages[0].text))

    monkeypatch.setattr(line, "process_turn", fake_process_turn)
    monkeypatch.setattr(line, "AsyncApiClient", FakeApiClient)
    monkeypatch.setattr(line, "AsyncMessagingApi", FakeMessagingApi)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=_settings(),
        background_tasks=background,
    )
    assert result == {"status": "ok", "queued": 1, "duplicate": 0, "skipped": 0}
    await background.run()
    assert sent == [("reply", "reply-token", "reply")]
    assert db.done == ["01FZ74A0TDDPYRVKNK77XKC3ZR"]


async def test_process_turn_failure_replies_with_fallback(monkeypatch):
    body = _line_body()
    sent = []
    background = FakeBackgroundTasks()
    db = FakeDB()

    async def fake_process_turn(**kwargs):
        raise RuntimeError("anthropic outage")

    class FakeApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeMessagingApi:
        def __init__(self, api_client):
            self.api_client = api_client

        async def reply_message(self, request):
            sent.append(("reply", request.reply_token, request.messages[0].text))

        async def push_message(self, request):
            sent.append(("push", request.to, request.messages[0].text))

    monkeypatch.setattr(line, "process_turn", fake_process_turn)
    monkeypatch.setattr(line, "AsyncApiClient", FakeApiClient)
    monkeypatch.setattr(line, "AsyncMessagingApi", FakeMessagingApi)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=_settings(),
        background_tasks=background,
    )
    assert result == {"status": "ok", "queued": 1, "duplicate": 0, "skipped": 0}
    await background.run()
    assert sent == [("reply", "reply-token", line.INTERVIEW_ERROR_REPLY)]
    assert db.failed == [("01FZ74A0TDDPYRVKNK77XKC3ZR", "anthropic outage")]


async def test_malformed_signature_is_graceful():
    body = _line_body()
    result = await line.handle_line_webhook(
        FakeRequest(body, "%%%not-base64%%%"),
        object(),
        object(),
        object(),
        settings=_settings(),
    )
    assert result == {"status": "invalid_signature"}


async def test_text_event_without_reply_token_skips(monkeypatch):
    body = _line_body(reply_token=None)

    async def fake_process_turn(**kwargs):
        raise AssertionError("should not call process_turn")

    monkeypatch.setattr(line, "process_turn", fake_process_turn)
    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        object(),
        object(),
        settings=_settings(),
    )
    assert result == {"status": "ok", "queued": 0, "duplicate": 0, "skipped": 1}


async def test_text_event_without_stable_event_id_skips(monkeypatch):
    body = _line_body()
    event = line.WebhookParser("secret").parse(body.decode(), _signature(body))[0]
    object.__setattr__(event, "webhook_event_id", None)
    object.__setattr__(event.message, "id", None)

    class FakeParser:
        def __init__(self, secret):
            self.secret = secret

        def parse(self, body_text, signature):
            return [event]

    async def fake_process_turn(**kwargs):
        raise AssertionError("should not call process_turn")

    monkeypatch.setattr(line, "WebhookParser", FakeParser)
    monkeypatch.setattr(line, "process_turn", fake_process_turn)
    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        object(),
        object(),
        settings=_settings(),
    )
    assert result == {"status": "ok", "queued": 0, "duplicate": 0, "skipped": 1}


async def test_duplicate_line_event_is_not_enqueued(monkeypatch):
    body = _line_body()
    background = FakeBackgroundTasks()
    db = FakeDB()
    assert await db.claim_transport_event("01FZ74A0TDDPYRVKNK77XKC3ZR", "line", "U123", "m1")

    async def fake_process_turn(**kwargs):
        raise AssertionError("duplicate event should not be processed")

    monkeypatch.setattr(line, "process_turn", fake_process_turn)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=_settings(),
        background_tasks=background,
    )

    assert result == {"status": "ok", "queued": 0, "duplicate": 1, "skipped": 0}
    assert background.tasks == []


async def test_reply_failure_uses_push_fallback():
    sent = []

    class FakeMessagingApi:
        async def reply_message(self, request):
            raise RuntimeError("expired")

        async def push_message(self, request):
            sent.append((request.to, request.messages[0].text))

    assert await line._send_reply_or_push(FakeMessagingApi(), "reply-token", "U123", "reply")
    assert sent == [("U123", "reply")]


async def test_unknown_user_without_session_is_rejected_before_enqueue(monkeypatch):
    body = _line_body()
    background = FakeBackgroundTasks()
    db = FakeDB(has_existing_session=False)
    settings = _settings()
    settings.line_interview_allowlist = "U999"
    settings.owner_line_user_id = "UOWNER"
    replies = []

    async def fake_direct_reply(access_token, reply_token, user_id, reply):
        replies.append((access_token, reply_token, user_id, reply))
        return True

    async def fail_process_text_event(**kwargs):
        raise AssertionError("rejected user must not be enqueued")

    monkeypatch.setattr(line, "_send_direct_text_reply", fake_direct_reply)
    monkeypatch.setattr(line, "_process_text_event", fail_process_text_event)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=settings,
        background_tasks=background,
    )

    assert result == {"status": "ok", "queued": 0, "duplicate": 0, "skipped": 1}
    assert background.tasks == []
    assert db.claimed == set()
    assert db.session_lookups == ["U123"]
    assert replies == [("token", "reply-token", "U123", line.INTERVIEW_CLOSED_REPLY)]


async def test_unknown_user_with_existing_session_is_allowed(monkeypatch):
    body = _line_body()
    background = FakeBackgroundTasks()
    db = FakeDB(has_existing_session=True)
    processed = []

    async def fake_process_text_event(**kwargs):
        processed.append(kwargs["interviewee_id"])

    monkeypatch.setattr(line, "_process_text_event", fake_process_text_event)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=_settings(),
        background_tasks=background,
    )
    await background.run()

    assert result == {"status": "ok", "queued": 1, "duplicate": 0, "skipped": 0}
    assert db.session_lookups == ["U123"]
    assert processed == ["U123"]


async def test_owner_is_allowed_when_interview_allowlist_is_empty(monkeypatch):
    body = _line_body()
    background = FakeBackgroundTasks()
    db = FakeDB(has_existing_session=False)
    settings = _settings()
    settings.owner_line_user_id = "U123"
    processed = []

    async def fake_process_text_event(**kwargs):
        processed.append(kwargs["interviewee_id"])

    monkeypatch.setattr(line, "_process_text_event", fake_process_text_event)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=settings,
        background_tasks=background,
    )
    await background.run()

    assert result == {"status": "ok", "queued": 1, "duplicate": 0, "skipped": 0}
    assert db.session_lookups == []
    assert processed == ["U123"]


async def test_empty_allowlist_and_owner_reject_new_user(monkeypatch):
    body = _line_body()
    background = FakeBackgroundTasks()
    db = FakeDB(has_existing_session=False)
    replies = []

    async def fake_direct_reply(access_token, reply_token, user_id, reply):
        replies.append((access_token, reply_token, user_id, reply))
        return True

    monkeypatch.setattr(line, "_send_direct_text_reply", fake_direct_reply)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=_settings(),
        background_tasks=background,
    )

    assert result == {"status": "ok", "queued": 0, "duplicate": 0, "skipped": 1}
    assert background.tasks == []
    assert db.claimed == set()
    assert replies == [("token", "reply-token", "U123", line.INTERVIEW_CLOSED_REPLY)]


async def test_allowlisted_user_is_allowed_without_session_lookup(monkeypatch):
    body = _line_body()
    background = FakeBackgroundTasks()
    db = FakeDB(has_existing_session=False)
    settings = _settings()
    settings.line_interview_allowlist = " U999, U123 ,U456 "
    processed = []

    async def fake_process_text_event(**kwargs):
        processed.append(kwargs["interviewee_id"])

    monkeypatch.setattr(line, "_process_text_event", fake_process_text_event)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=settings,
        background_tasks=background,
    )
    await background.run()

    assert result == {"status": "ok", "queued": 1, "duplicate": 0, "skipped": 0}
    assert db.session_lookups == []
    assert processed == ["U123"]


async def test_session_lookup_error_fails_closed(monkeypatch, caplog):
    body = _line_body()
    background = FakeBackgroundTasks()
    db = FakeDB(session_lookup_error=RuntimeError("database unavailable"))
    replies = []

    async def fake_direct_reply(access_token, reply_token, user_id, reply):
        replies.append((access_token, reply_token, user_id, reply))
        return True

    monkeypatch.setattr(line, "_send_direct_text_reply", fake_direct_reply)

    result = await line.handle_line_webhook(
        FakeRequest(body, _signature(body)),
        object(),
        db,
        object(),
        settings=_settings(),
        background_tasks=background,
    )

    assert result == {"status": "ok", "queued": 0, "duplicate": 0, "skipped": 1}
    assert background.tasks == []
    assert db.claimed == set()
    assert "session lookup failed" in caplog.text
    assert replies == [("token", "reply-token", "U123", line.INTERVIEW_CLOSED_REPLY)]
