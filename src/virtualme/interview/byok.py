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
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from anthropic import (
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    UnprocessableEntityError,
)

from virtualme.interview.models import MODEL_FAST, create_message

logger = logging.getLogger(__name__)

KEY_PREFIX = "sk-ant-"
CONSENT_TEXT = "同意"

# Canned gate replies. These are static strings: returning one costs zero LLM
# calls and writes zero turns, which the gate flow depends on.
ONBOARDING_REPLY = (
    "我是 VirtualMe 人格萃取機器人。開始之前，"  # noqa: RUF001
    "請先提供您的 Claude API Key（sk-ant- 開頭）。"  # noqa: RUF001
)
CONSENT_REPLY = (
    "開始前請先確認並回覆「同意」。\n\n"
    "1. 訪談資料會儲存在 Maki 的 VPS 上。\n"
    "2. Maki 不會主動讀取您的訪談內容或行為模式檔; "
    "除非您要求 Maki 介入判斷或協助 review。\n"
    "3. 請自行移除不想留下的個人資料或第三人個資; "
    "系統不會替您改寫或置換人名。\n"
    "4. 若要刪除資料, 請明確指定範圍: 訪談問答 / 行為模式檔 / Claude API Key。"
    "我不會主動亂刪。\n"
    "5. 產出的檔案稱為「行為模式檔」, 不是診斷、不是定論, "
    "只是從訪談中萃取出的特質與行為模式草稿。\n\n"
    "若接受以上說明, 請回覆「同意」。"
)
CONSENT_ACCEPTED_REPLY = (
    "已記錄同意。接下來請提供您的 Claude API Key (sk-ant- 開頭) 以開始訪談。"
)
KEY_ACCEPTED_REPLY = "API Key 驗證成功，開始訪談。請說說您最近的工作狀況。"  # noqa: RUF001
KEY_INVALID_REPLY = "API Key 無效，請重新提供。"  # noqa: RUF001


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


def has_key(keys_dir: str, interviewee_id: str) -> bool:
    return _key_path(keys_dir, interviewee_id).is_file()


def has_consent(keys_dir: str, interviewee_id: str) -> bool:
    return _consent_path(keys_dir, interviewee_id).is_file()


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


def store_consent(keys_dir: str, interviewee_id: str) -> None:
    dir_path = Path(keys_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    os.chmod(dir_path, 0o700)
    path = _consent_path(keys_dir, interviewee_id)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("agreed")
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


def run_consent_gate(interviewee_id: str, incoming_message: str, keys_dir: str) -> str | None:
    """Require data-use consent before any session/turn/LLM work.

    Consent is intentionally independent from BYOK: operator-key deployments
    still collect and store interview data, so they need the same disclosure.
    """
    if has_consent(keys_dir, interviewee_id):
        return None
    if incoming_message.strip() == CONSENT_TEXT:
        store_consent(keys_dir, interviewee_id)
        logger.info("Consent gate: consent accepted for %s", interviewee_id)
        return CONSENT_ACCEPTED_REPLY
    logger.info("Consent gate: consent prompt sent to %s", interviewee_id)
    return CONSENT_REPLY


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
