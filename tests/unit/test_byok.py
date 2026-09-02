"""Tests for the BW5 BYOK gate."""

import hashlib
import json
import logging
import stat

import aiosqlite
import httpx
import pytest
from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.interview import byok
from virtualme.interview.bot import process_turn
from virtualme.interview.crisis import CRISIS_HELPLINE_EXAMPLES_ZH, CRISIS_REPLY
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB, Dimension, Question


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    """Mock Anthropic messages API covering every call shape in process_turn."""

    def __init__(self):
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        max_tokens = kwargs["max_tokens"]
        if max_tokens == 120:
            text = json.dumps(
                {
                    "kind": "SUFFICIENT",
                    "depth": "principle",
                    "needs_follow_up": False,
                    "confidence": 0.9,
                }
            )
        elif max_tokens in (500, 900):
            text = "[]"
        else:
            text = "OK"
        return type("Response", (), {"content": [_Content(text)]})


class _Claude:
    def __init__(self):
        self.messages = _Messages()


def _selector() -> QuestionSelector:
    return QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="How has work been?")]}
    )


def _settings(keys_dir) -> Settings:
    return Settings(
        anthropic_api_key=SecretStr("operator-key"),
        byok_enabled=True,
        consent_required=False,
        byok_keys_dir=str(keys_dir),
    )


async def _new_db(tmp_path) -> DB:
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    return db


async def _count(db: DB, table: str) -> int:
    async with aiosqlite.connect(db.path) as conn:
        return (await (await conn.execute(f"SELECT COUNT(*) FROM {table}")).fetchone())[0]


def _write_consent_fixture(keys_dir, interviewee_id: str, content: str):
    keys_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(interviewee_id.encode("utf-8")).hexdigest()
    path = keys_dir / f"{digest}.consent"
    path.write_text(content, encoding="utf-8")
    return path


# --- gate-level tests --------------------------------------------------------


def test_consent_gate_prompts_before_any_storage(tmp_path):
    keys_dir = tmp_path / "keys"

    reply = byok.run_consent_gate("u1", "hello there", str(keys_dir), byok_enabled=True)

    assert reply == byok.render_consent_reply("operator")
    assert not byok.has_consent(str(keys_dir), "u1")
    assert not keys_dir.exists()


def test_consent_gate_accepts_exact_consent_with_restrictive_modes(tmp_path):
    keys_dir = tmp_path / "keys"

    reply = byok.run_consent_gate("u1", byok.CONSENT_TEXT, str(keys_dir), byok_enabled=True)

    assert reply == byok.CONSENT_ACCEPTED_REPLY
    assert byok.has_consent(str(keys_dir), "u1")
    consent_files = list(keys_dir.glob("*.consent"))
    assert len(consent_files) == 1
    record = json.loads(consent_files[0].read_text(encoding="utf-8"))
    assert record["version"] == byok.CONSENT_VERSION
    rendered_consent = byok.render_consent_reply("operator")
    assert record["text_sha256"] == hashlib.sha256(rendered_consent.encode("utf-8")).hexdigest()
    assert record["agreed_at"].endswith("+00:00")
    assert record["age_confirmed"] is True
    assert stat.S_IMODE(consent_files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o700


def test_consent_gate_existing_consent_allows_turn_to_continue(tmp_path):
    keys_dir = tmp_path / "keys"
    byok.store_consent(str(keys_dir), "u1")

    assert byok.run_consent_gate("u1", "a normal answer", str(keys_dir), byok_enabled=True) is None


def test_consent_reply_covers_required_terms_and_shared_crisis_resources():
    operator_display_name = "測試營運方"
    reply = byok.render_consent_reply(operator_display_name)
    required_terms = (
        "therapist-style",
        "我是 AI",
        "不是心理師",
        "不是心理治療",
        "不是心理諮商",
        "童年",
        "創傷",
        "未解決的決定",
        "skip",
        "換題",
        "累了",
        "這段不要存",
        "品質抽查",
        "逐字稿",
        "其他人看不到",
        "自傷",
        "自殺意念",
        "無法承受的痛苦",
        "停止",
        "專業協助",
        "1925",
        "危機層",
        "AI 代理人",
        "保留部分",
        "全部刪除",
        "修改",
        "8 週",
        "上線",
        "法律上",
        "社會上",
        "責任上",
        "屬於你",
        "不屬於 AI",
        "撤回",
        "24 小時",
        "年滿 18 歲",
        "VirtualMe" + "\uff0f" + "千葉熊",
        "Anthropic API",
        "API key",
        "跨境傳輸",
        operator_display_name,
    )

    assert all(term in reply for term in required_terms)
    assert CRISIS_HELPLINE_EXAMPLES_ZH in reply
    assert CRISIS_HELPLINE_EXAMPLES_ZH in CRISIS_REPLY
    assert "Maki" not in reply


@pytest.mark.parametrize(
    "message",
    [
        byok.CONSENT_TEXT,
        "我已滿１８歲" + "\uff0c" + "同意開始",
        "我已滿 18 歲" + "\uff0c" + "同意開始",
        "我年滿18歲" + "\uff0c" + "同意開始",
        "我年滿１８岁" + "\uff0c" + "同意開始",
        "我年滿 18 岁" + "\uff0c" + "同意開始。",
        "我已滿18歲, 同意開始!",
    ],
)
def test_consent_gate_accepts_age_confirming_variants(tmp_path, message):
    keys_dir = tmp_path / "keys"

    reply = byok.run_consent_gate("u1", message, str(keys_dir), byok_enabled=True)

    assert reply == byok.CONSENT_ACCEPTED_REPLY
    assert byok.has_consent(str(keys_dir), "u1")


@pytest.mark.parametrize("message", ["同意", "ok", "我同意"])
def test_consent_gate_rejects_messages_without_age_confirmation(tmp_path, message):
    keys_dir = tmp_path / "keys"

    reply = byok.run_consent_gate("u1", message, str(keys_dir), byok_enabled=True)

    assert reply == byok.render_consent_reply("operator")
    assert not byok.has_consent(str(keys_dir), "u1")


def test_consent_gate_reprompts_old_version_json(tmp_path):
    keys_dir = tmp_path / "keys"
    _write_consent_fixture(
        keys_dir,
        "u1",
        json.dumps({"version": "2026-08-31", "age_confirmed": True}),
    )

    reply = byok.run_consent_gate("u1", "a normal answer", str(keys_dir), byok_enabled=True)

    assert reply == byok.render_consent_reply("operator")
    assert not byok.has_consent(str(keys_dir), "u1")


def test_operator_display_name_changes_consent_reply(tmp_path):
    keys_dir = tmp_path / "keys"

    first = byok.run_consent_gate(
        "u1", "hello", str(keys_dir), byok_enabled=True, operator_display_name="甲方主機"
    )
    second = byok.run_consent_gate(
        "u2", "hello", str(keys_dir), byok_enabled=True, operator_display_name="乙方主機"
    )

    assert first != second
    assert first is not None and "甲方主機" in first and "乙方主機" not in first
    assert second is not None and "乙方主機" in second and "甲方主機" not in second


async def test_gate_no_key_normal_message_returns_onboarding(tmp_path):
    keys_dir = tmp_path / "keys"
    result = await byok.run_byok_gate("u1", "hello there", str(keys_dir))
    assert result.reply == byok.ONBOARDING_REPLY
    assert result.api_key is None
    assert not keys_dir.exists()


async def test_gate_invalid_key_is_not_stored(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    calls: list[str] = []

    async def fake_validate(key: str) -> bool:
        calls.append(key)
        return False

    monkeypatch.setattr(byok, "validate_api_key", fake_validate)
    result = await byok.run_byok_gate("u1", "sk-ant-bad", str(keys_dir))

    assert result.reply == byok.KEY_INVALID_REPLY
    assert result.api_key is None
    assert calls == ["sk-ant-bad"]
    assert not byok.has_key(str(keys_dir), "u1")


async def test_gate_valid_key_stored_with_restrictive_modes(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"

    async def fake_validate(_key: str) -> bool:
        return True

    monkeypatch.setattr(byok, "validate_api_key", fake_validate)
    result = await byok.run_byok_gate("u1", "  sk-ant-good123  ", str(keys_dir))

    assert result.reply == byok.KEY_ACCEPTED_REPLY
    key_files = list(keys_dir.glob("*.key"))
    assert len(key_files) == 1
    assert key_files[0].read_text(encoding="utf-8") == "sk-ant-good123"
    assert stat.S_IMODE(key_files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o700


async def test_gate_existing_key_proceeds(tmp_path):
    keys_dir = tmp_path / "keys"
    byok.store_key(str(keys_dir), "u1", "sk-ant-existing")
    result = await byok.run_byok_gate("u1", "a normal interview answer", str(keys_dir))
    assert result.reply is None
    assert result.api_key == "sk-ant-existing"


async def test_gate_never_logs_the_key(tmp_path, monkeypatch, caplog):
    keys_dir = tmp_path / "keys"

    async def fake_validate(_key: str) -> bool:
        return True

    monkeypatch.setattr(byok, "validate_api_key", fake_validate)
    secret = "sk-ant-secret-value-do-not-log-xyz"
    with caplog.at_level(logging.DEBUG):
        await byok.run_byok_gate("u1", secret, str(keys_dir))
    assert secret not in caplog.text


async def test_validate_api_key_treats_malformed_4xx_as_invalid(monkeypatch):
    class BadClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        class messages:
            @staticmethod
            async def create(**_kwargs):
                response = httpx.Response(400, request=httpx.Request("POST", "https://api.test"))
                raise byok.BadRequestError("bad request", response=response, body={})

    monkeypatch.setattr(byok, "build_client", lambda _key: BadClient())

    assert await byok.validate_api_key("sk-ant-malformed") is False


async def test_validate_api_key_treats_unprocessable_4xx_as_invalid(monkeypatch):
    class BadClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        class messages:
            @staticmethod
            async def create(**_kwargs):
                response = httpx.Response(422, request=httpx.Request("POST", "https://api.test"))
                raise byok.UnprocessableEntityError("bad key", response=response, body={})

    monkeypatch.setattr(byok, "build_client", lambda _key: BadClient())

    assert await byok.validate_api_key("sk-ant-malformed") is False


# --- process_turn integration ------------------------------------------------


async def test_process_turn_onboarding_writes_no_turns_no_llm(tmp_path, monkeypatch):
    db = await _new_db(tmp_path)
    settings = _settings(tmp_path / "keys")

    def boom(_key):
        raise AssertionError("LLM client must not be built before a key is provided")

    monkeypatch.setattr(byok, "build_client", boom)
    reply = await process_turn("u1", "hello", object(), db, _selector(), settings)

    assert reply == byok.ONBOARDING_REPLY
    assert await _count(db, "turns") == 0
    assert await _count(db, "sessions") == 0


async def test_process_turn_consent_required_before_byok_onboarding(tmp_path, monkeypatch):
    db = await _new_db(tmp_path)
    settings = Settings(
        anthropic_api_key=SecretStr("operator-key"),
        byok_enabled=True,
        consent_required=True,
        byok_keys_dir=str(tmp_path / "keys"),
    )

    def boom(_key):
        raise AssertionError("LLM client must not be built before consent")

    monkeypatch.setattr(byok, "build_client", boom)
    reply = await process_turn("u1", "hello", object(), db, _selector(), settings)

    assert reply == byok.render_consent_reply("operator")
    assert await _count(db, "turns") == 0
    assert await _count(db, "sessions") == 0


async def test_process_turn_consent_required_with_operator_key(tmp_path):
    db = await _new_db(tmp_path)
    settings = Settings(
        anthropic_api_key=SecretStr("operator-key"),
        byok_enabled=False,
        consent_required=True,
        byok_keys_dir=str(tmp_path / "keys"),
        operator_display_name="測試營運方",
    )
    operator_client = _Claude()

    reply = await process_turn("u1", "hello", operator_client, db, _selector(), settings)

    assert reply == byok.render_consent_reply("測試營運方")
    assert operator_client.messages.calls == 0
    assert await _count(db, "turns") == 0
    assert await _count(db, "sessions") == 0


async def test_process_turn_existing_key_still_requires_consent(tmp_path, monkeypatch):
    db = await _new_db(tmp_path)
    settings = Settings(
        anthropic_api_key=SecretStr("operator-key"),
        byok_enabled=True,
        consent_required=True,
        byok_keys_dir=str(tmp_path / "keys"),
    )
    byok.store_key(settings.byok_keys_dir, "u1", "sk-ant-existing")
    interviewee_client = _Claude()
    monkeypatch.setattr(byok, "build_client", lambda _key: interviewee_client)

    reply = await process_turn("u1", "a normal answer", object(), db, _selector(), settings)

    assert reply == byok.render_consent_reply("operator")
    assert interviewee_client.messages.calls == 0
    assert await _count(db, "turns") == 0
    assert await _count(db, "sessions") == 0


async def test_process_turn_consent_acceptance_writes_no_turns(tmp_path):
    db = await _new_db(tmp_path)
    settings = Settings(
        anthropic_api_key=SecretStr("operator-key"),
        byok_enabled=False,
        consent_required=True,
        byok_keys_dir=str(tmp_path / "keys"),
    )

    reply = await process_turn("u1", byok.CONSENT_TEXT, object(), db, _selector(), settings)

    assert reply == byok.CONSENT_ACCEPTED_REPLY_OPERATOR
    assert byok.has_consent(settings.byok_keys_dir, "u1")
    assert await _count(db, "turns") == 0
    assert await _count(db, "sessions") == 0


async def test_process_turn_legacy_consent_reprompts_without_turns_or_llm(tmp_path):
    db = await _new_db(tmp_path)
    keys_dir = tmp_path / "keys"
    _write_consent_fixture(keys_dir, "u1", "agreed")
    settings = Settings(
        anthropic_api_key=SecretStr("operator-key"),
        byok_enabled=False,
        consent_required=True,
        byok_keys_dir=str(keys_dir),
    )
    operator_client = _Claude()

    reply = await process_turn("u1", "a normal answer", operator_client, db, _selector(), settings)

    assert reply == byok.render_consent_reply("operator")
    assert operator_client.messages.calls == 0
    assert await _count(db, "turns") == 0
    assert await _count(db, "sessions") == 0


async def test_process_turn_invalid_key_writes_no_turns(tmp_path, monkeypatch):
    db = await _new_db(tmp_path)
    settings = _settings(tmp_path / "keys")

    async def fake_validate(_key: str) -> bool:
        return False

    monkeypatch.setattr(byok, "validate_api_key", fake_validate)
    reply = await process_turn("u1", "sk-ant-bad", object(), db, _selector(), settings)

    assert reply == byok.KEY_INVALID_REPLY
    assert await _count(db, "turns") == 0
    assert not byok.has_key(settings.byok_keys_dir, "u1")


async def test_process_turn_valid_key_stores_and_writes_no_turns(tmp_path, monkeypatch):
    db = await _new_db(tmp_path)
    settings = _settings(tmp_path / "keys")

    async def fake_validate(_key: str) -> bool:
        return True

    monkeypatch.setattr(byok, "validate_api_key", fake_validate)
    reply = await process_turn("u1", "sk-ant-good", object(), db, _selector(), settings)

    assert reply == byok.KEY_ACCEPTED_REPLY
    assert byok.has_key(settings.byok_keys_dir, "u1")
    assert await _count(db, "turns") == 0


async def test_process_turn_existing_key_runs_extraction_on_interviewee_client(
    tmp_path, monkeypatch
):
    db = await _new_db(tmp_path)
    settings = _settings(tmp_path / "keys")
    byok.store_key(settings.byok_keys_dir, "u1", "sk-ant-existing")

    interviewee_client = _Claude()
    monkeypatch.setattr(byok, "build_client", lambda key: interviewee_client)

    reply = await process_turn(
        "u1", "When I work, I prefer direct evidence.", object(), db, _selector(), settings
    )

    assert reply
    assert interviewee_client.messages.calls > 0
    turns = await db.load_session_turns(1)
    roles = [turn.role for turn in turns]
    assert "user" in roles and "assistant" in roles


async def test_process_turn_revoke_key_bypasses_consent_and_deletes_key(tmp_path, monkeypatch):
    db = await _new_db(tmp_path)
    settings = Settings(
        anthropic_api_key=SecretStr("operator-key"),
        byok_enabled=True,
        consent_required=True,
        byok_keys_dir=str(tmp_path / "keys"),
    )
    byok.store_key(settings.byok_keys_dir, "u1", "sk-ant-existing")

    def boom(_key):
        raise AssertionError("LLM client must not be built for revoke command")

    monkeypatch.setattr(byok, "build_client", boom)
    reply = await process_turn("u1", "刪除 API Key", object(), db, _selector(), settings)

    assert "已刪除" in reply
    assert not byok.has_key(settings.byok_keys_dir, "u1")
    assert await _count(db, "turns") == 0
    assert await _count(db, "sessions") == 0


async def test_process_turn_revoke_key_works_when_byok_disabled(tmp_path):
    db = await _new_db(tmp_path)
    settings = Settings(
        anthropic_api_key=SecretStr("operator-key"),
        byok_enabled=False,
        consent_required=True,
        byok_keys_dir=str(tmp_path / "keys"),
    )
    byok.store_key(settings.byok_keys_dir, "u1", "sk-ant-existing")

    reply = await process_turn("u1", "刪除 API Key", object(), db, _selector(), settings)

    assert "已刪除" in reply
    assert not byok.has_key(settings.byok_keys_dir, "u1")
    assert await _count(db, "turns") == 0
    assert await _count(db, "sessions") == 0


async def test_byok_disabled_uses_passed_operator_client(tmp_path):
    db = await _new_db(tmp_path)
    settings = Settings(anthropic_api_key=SecretStr("operator-key"), byok_enabled=False)
    operator_client = _Claude()

    reply = await process_turn(
        "u1", "When I work, I prefer direct evidence.", operator_client, db, _selector(), settings
    )

    assert reply
    assert operator_client.messages.calls > 0
