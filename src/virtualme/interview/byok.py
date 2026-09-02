# ruff: noqa: RUF001
"""BYOK (Bring Your Own Key) gate for the interview path — BW5.

Each interviewee must provide their own Claude API key before extraction
begins. When BYOK is enabled the operator's key is never used for interview
LLM calls: every call in ``process_turn`` runs on the interviewee's key.

Key storage (BW5 D2, Chair ratified):

- ``<keys_dir>/<sha256(interviewee_id)>.key``, file mode 0600, dir mode 0700.
- Keys never enter SQLite, the turns transcript, or logs.
- Accepted risk: a full-machine snapshot compromise exposes stored keys.
  Interviewee keys are revocable and carry their own billing caps, so the
  blast radius is bounded. Production layers an off-box secret manager.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from anthropic import (
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    UnprocessableEntityError,
)

from virtualme.interview.crisis import CRISIS_HELPLINE_EXAMPLES_ZH
from virtualme.interview.models import MODEL_FAST, create_message

logger = logging.getLogger(__name__)

KEY_PREFIX = "sk-ant-"
CONSENT_TEXT = "我已滿18歲，同意開始"
CONSENT_VERSION = "2026-09-01"
_CONSENT_ACCEPTANCE_PATTERN = re.compile(
    r"^我(?:已滿|年滿)\s*18\s*[歲岁]\s*[,，]?\s*同意開始\s*[。.!！?？]*$"
)

# Canned gate replies. These are static strings: returning one costs zero LLM
# calls and writes zero turns, which the gate flow depends on.
ONBOARDING_REPLY = (
    "我是 VirtualMe 人格萃取機器人。開始之前，"
    "請先提供您的 Claude API Key（sk-ant- 開頭）。"
)
CONSENT_REPLY = f"""\
正式開始前，請先閱讀並確認以下訪談界線：

1. 我的方法是「therapist-style 深度訪談」：我會追問「為什麼」，直到你的判斷標準浮現。但我是 AI，不是心理師；這不是心理治療，也不是心理諮商。
2. 過程可能浮現你未曾注意的童年、創傷或未解決的決定。若你不舒服，隨時可以 skip、換題、說「累了」或說「這段不要存」。
3. 我會保密：只有 operator「{{operator_display_name}}」為了品質抽查可以查看訪談逐字稿，其他人看不到你說的內容。
4. 若出現自傷、自殺意念或無法承受的痛苦訊號，我會停止訪談並建議你尋求專業協助（{CRISIS_HELPLINE_EXAMPLES_ZH}）。我無法處理危機層。
5. 我們討論的內容最終會成為一個 AI 代理人。你隨時可以保留部分、全部刪除或修改某一段，並在 8 週後決定是否上線。
6. 代理人寫出的任何內容，在法律上、社會上與責任上都屬於你，不屬於 AI。
7. 你隨時可以撤回。撤回時可選擇保留或刪除對話紀錄；選擇刪除時，會在 24 小時內完成。
8. 本訪談僅限年滿 18 歲者參加。
9. 訪談內容儲存在 operator「{{operator_display_name}}」指定的主機，不會傳送到 VirtualMe／千葉熊的任何平台；但每則訊息在生成回覆時會經由 Anthropic API 處理（BYOK 模式使用你自己的 API key）。這屬跨境傳輸，請知悉。

若你理解並同意以上內容，請完整回覆「{CONSENT_TEXT}」。"""
CONSENT_ACCEPTED_REPLY = (
    "已記錄同意。接下來請提供您的 Claude API Key (sk-ant- 開頭) 以開始訪談。"
)
CONSENT_ACCEPTED_REPLY_OPERATOR = (
    "已記錄同意。我們現在就開始 —— 先跟我說說, 你最近的工作或生活, 過得怎麼樣?"
)
KEY_ACCEPTED_REPLY = "API Key 驗證成功，開始訪談。請說說您最近的工作狀況。"
KEY_INVALID_REPLY = "API Key 無效，請重新提供。"


@dataclass
class GateResult:
    """Outcome of the BYOK gate.

    Exactly one branch is meaningful:
    - ``reply`` set  -> stop ``process_turn`` and return this canned reply.
    - ``api_key`` set -> proceed; run interview LLM calls on this key.
    """

    reply: str | None
    api_key: str | None


def _key_path(keys_dir: str, interviewee_id: str) -> Path:
    # interviewee_id (e.g. a LINE user_id) is hashed so it is never used
    # verbatim as a filename and the directory listing leaks no identities.
    digest = hashlib.sha256(interviewee_id.encode("utf-8")).hexdigest()
    return Path(keys_dir) / f"{digest}.key"


def _consent_path(keys_dir: str, interviewee_id: str) -> Path:
    digest = hashlib.sha256(interviewee_id.encode("utf-8")).hexdigest()
    return Path(keys_dir) / f"{digest}.consent"


def render_consent_reply(operator_display_name: str) -> str:
    return CONSENT_REPLY.format(operator_display_name=operator_display_name)


def is_consent_acceptance(message: str) -> bool:
    normalized = unicodedata.normalize("NFKC", message).strip()
    return _CONSENT_ACCEPTANCE_PATTERN.fullmatch(normalized) is not None


def has_key(keys_dir: str, interviewee_id: str) -> bool:
    return _key_path(keys_dir, interviewee_id).is_file()


def has_consent(keys_dir: str, interviewee_id: str) -> bool:
    path = _consent_path(keys_dir, interviewee_id)
    if not path.is_file():
        return False
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        return False
    return isinstance(record, dict) and record.get("version") == CONSENT_VERSION


def read_key(keys_dir: str, interviewee_id: str) -> str | None:
    path = _key_path(keys_dir, interviewee_id)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip()


def store_key(keys_dir: str, interviewee_id: str, api_key: str) -> None:
    """Persist a key with 0700 dir / 0600 file. Created restricted from birth."""
    dir_path = Path(keys_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    os.chmod(dir_path, 0o700)
    path = _key_path(keys_dir, interviewee_id)
    # Open with 0600 directly to avoid any window where the file is readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(api_key.strip())
    os.chmod(path, 0o600)


def store_consent(
    keys_dir: str,
    interviewee_id: str,
    consent_text: str | None = None,
) -> None:
    dir_path = Path(keys_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    os.chmod(dir_path, 0o700)
    path = _consent_path(keys_dir, interviewee_id)
    rendered_consent = (
        consent_text if consent_text is not None else render_consent_reply("operator")
    )
    record = {
        "version": CONSENT_VERSION,
        "text_sha256": hashlib.sha256(rendered_consent.encode("utf-8")).hexdigest(),
        "agreed_at": datetime.now(UTC).isoformat(),
        "age_confirmed": True,
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False)
    os.chmod(path, 0o600)


def delete_key(keys_dir: str, interviewee_id: str) -> bool:
    """Revoke a stored key. Returns True if a key file was removed."""
    path = _key_path(keys_dir, interviewee_id)
    if path.is_file():
        path.unlink()
        return True
    return False


def build_client(api_key: str) -> AsyncAnthropic:
    """Construct a per-interviewee Anthropic client.

    Built fresh per turn (never cached) so the key's in-memory lifetime stays
    minimal and key rotation/revocation takes effect on the next message.
    """
    return AsyncAnthropic(api_key=api_key, max_retries=4)


async def validate_api_key(api_key: str) -> bool:
    """1-token test call. True if the key authenticates.

    Auth-class failures return False (the key is genuinely bad). Transient or
    non-auth errors propagate so a working key is never mislabelled invalid
    during an outage.
    """
    async with build_client(api_key) as client:
        try:
            await create_message(
                client,
                model=MODEL_FAST,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
        except (
            AuthenticationError,
            PermissionDeniedError,
            BadRequestError,
            UnprocessableEntityError,
        ):
            return False
    return True


def run_consent_gate(
    interviewee_id: str,
    incoming_message: str,
    keys_dir: str,
    byok_enabled: bool,
    operator_display_name: str = "operator",
) -> str | None:
    """Require data-use consent before any session/turn/LLM work.

    Consent is intentionally independent from BYOK: operator-key deployments
    still collect and store interview data, so they need the same disclosure.
    """
    if has_consent(keys_dir, interviewee_id):
        return None
    consent_reply = render_consent_reply(operator_display_name)
    if is_consent_acceptance(incoming_message):
        store_consent(keys_dir, interviewee_id, consent_reply)
        logger.info("Consent gate: consent accepted for %s", interviewee_id)
        if byok_enabled:
            return CONSENT_ACCEPTED_REPLY
        return CONSENT_ACCEPTED_REPLY_OPERATOR
    logger.info("Consent gate: consent prompt sent to %s", interviewee_id)
    return consent_reply


async def run_byok_gate(
    interviewee_id: str,
    incoming_message: str,
    keys_dir: str,
) -> GateResult:
    """Decide whether the interview may proceed for this turn.

    Logs only the interviewee_id and the result — never the key itself.
    """
    existing = read_key(keys_dir, interviewee_id)
    if existing:
        return GateResult(reply=None, api_key=existing)

    candidate = incoming_message.strip()
    if not candidate.startswith(KEY_PREFIX):
        logger.info("BYOK gate: onboarding prompt sent to %s", interviewee_id)
        return GateResult(reply=ONBOARDING_REPLY, api_key=None)

    if await validate_api_key(candidate):
        store_key(keys_dir, interviewee_id, candidate)
        logger.info("BYOK gate: key accepted and stored for %s", interviewee_id)
        return GateResult(reply=KEY_ACCEPTED_REPLY, api_key=None)

    logger.info("BYOK gate: key rejected for %s", interviewee_id)
    return GateResult(reply=KEY_INVALID_REPLY, api_key=None)
