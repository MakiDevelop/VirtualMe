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

from anthropic import AsyncAnthropic, AuthenticationError, PermissionDeniedError

from virtualme.interview.models import MODEL_FAST

logger = logging.getLogger(__name__)

KEY_PREFIX = "sk-ant-"

# Canned gate replies. These are static strings: returning one costs zero LLM
# calls and writes zero turns, which the gate flow depends on.
ONBOARDING_REPLY = (
    "我是 VirtualMe 人格萃取機器人。開始之前，"  # noqa: RUF001
    "請先提供您的 Claude API Key（sk-ant- 開頭）。"  # noqa: RUF001
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


def has_key(keys_dir: str, interviewee_id: str) -> bool:
    return _key_path(keys_dir, interviewee_id).is_file()


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
            await client.messages.create(
                model=MODEL_FAST,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
        except (AuthenticationError, PermissionDeniedError):
            return False
    return True


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
