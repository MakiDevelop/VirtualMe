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
        object(),
        object(),
        settings=_settings(),
    )
    assert result == {"status": "ok", "handled": 1}
    assert sent == [("reply", "reply-token", "reply")]


async def test_process_turn_failure_replies_with_fallback(monkeypatch):
    body = _line_body()
    sent = []

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
        object(),
        object(),
        settings=_settings(),
    )
    assert result == {"status": "ok", "handled": 1}
    assert sent == [("reply", "reply-token", line.INTERVIEW_ERROR_REPLY)]


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
    assert result == {"status": "ok", "handled": 0}


async def test_reply_failure_uses_push_fallback():
    sent = []

    class FakeMessagingApi:
        async def reply_message(self, request):
            raise RuntimeError("expired")

        async def push_message(self, request):
            sent.append((request.to, request.messages[0].text))

    assert await line._send_reply_or_push(FakeMessagingApi(), "reply-token", "U123", "reply")
    assert sent == [("U123", "reply")]
