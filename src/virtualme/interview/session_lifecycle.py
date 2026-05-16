"""Session completion and stale-session finalization.

Interview triples are only useful once a session has enough context and a clear stopping point.
This module centralizes the cheap lifecycle heuristics that decide when to run the existing triple
extractor and mark a session complete. Known limitations: phrase matching can miss indirect exits,
sarcasm, code-switching, and voice/audio-only endings; stale-session finalization depends on DB
timestamps and should later be moved to a real scheduler. The trade-off is intentional for v0.4.1:
simple local checks avoid extra dependencies and reduce accidental Claude calls during active chat.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from anthropic import AsyncAnthropic

from virtualme.interview.triples import extract_triples_from_session
from virtualme.storage.db import DB, Turn

logger = logging.getLogger(__name__)

CLOSING_PHRASES_USER = [
    "累了",
    "再見",
    "下次聊",
    "先這樣",
    "今天先這樣",
    "end session",
    "bye",
    "goodbye",
    "see you",
    "that's all",
    "tired",
    "i'm done",
    "let's stop",
]

# After stripping recognised closing phrases, a genuine closing message has
# little left. This guards against a closing word buried in a longer sentence
# (e.g. "bye is what I never say" must NOT end the session).
CLOSING_RESIDUAL_MAX = 4


def is_session_closing(user_text: str) -> bool:
    lowered = user_text.lower().strip()
    if not lowered:
        return False
    matched = [phrase for phrase in CLOSING_PHRASES_USER if phrase in lowered]
    if not matched:
        return False
    residual = lowered
    # remove longest phrases first so nested phrases are fully consumed
    for phrase in sorted(matched, key=len, reverse=True):
        residual = residual.replace(phrase, "")
    residual = re.sub(r"[\W_]", "", residual)
    return len(residual) <= CLOSING_RESIDUAL_MAX


def is_session_stale(last_turn_at: datetime, threshold_minutes: int = 30) -> bool:
    now = datetime.now(UTC)
    last_seen = last_turn_at if last_turn_at.tzinfo else last_turn_at.replace(tzinfo=UTC)
    return now - last_seen >= timedelta(minutes=threshold_minutes)


async def finalize_session_if_closing(
    session_id: int,
    interviewee_id: str,
    user_text: str,
    turns: list[Turn],
    claude: AsyncAnthropic,
    db: DB,
) -> int:
    if not is_session_closing(user_text):
        return 0

    extracted = await _extract_and_complete(session_id, interviewee_id, turns, claude, db)
    logger.info("Session %s closed by turn pair; extracted %s triples", session_id, extracted)
    return extracted


async def finalize_stale_sessions(
    db: DB,
    claude: AsyncAnthropic,
    threshold_minutes: int = 30,
) -> int:
    finalized = 0
    for session in await db.load_stale_active_sessions(threshold_minutes):
        turns = await db.load_session_turns(session.id)
        finalized += await _extract_and_complete(session.id, session.interviewee_id, turns, claude, db)
        logger.info("Session %s closed by inactivity timeout", session.id)
    return finalized


async def _extract_and_complete(
    session_id: int,
    interviewee_id: str,
    turns: list[Turn],
    claude: AsyncAnthropic,
    db: DB,
) -> int:
    triples = await extract_triples_from_session(session_id, turns, claude)
    for triple in triples:
        triple.interviewee_id = interviewee_id
        await db.save_triple(triple)
    await db.mark_session_completed(session_id)
    return len(triples)
