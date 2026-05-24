"""Multi-session validation gate -- Constitution v1.1 §P4 hard gate.

Decides whether an anchor's source evidence spans multiple sessions, which
is the prerequisite for promoting it to a "validated" stable trait.

P4 M1 baseline (negative constraint only): single-session anchors must
never be presented as validated stable traits, regardless of how many
unique question_ids they cover.

This module provides detection helpers only. Runtime promotion-gate
integration is deferred to M2.
"""

from __future__ import annotations

from virtualme.storage.db import DB, Anchor


async def unique_session_count(db: DB, turn_ids: list[int]) -> int:
    """Return the number of unique session_ids covered by these turns.

    Returns 0 if turn_ids is empty or no matching turns are found. Invalid
    turn ids are ignored by the database query.
    """
    if not turn_ids:
        return 0

    placeholders = ", ".join("?" for _ in turn_ids)
    async with db._connect() as conn:
        row = await (
            await conn.execute(
                f"""
                SELECT COUNT(DISTINCT session_id)
                FROM turns
                WHERE id IN ({placeholders})
                """,
                tuple(turn_ids),
            )
        ).fetchone()

    return int(row[0]) if row and row[0] is not None else 0


async def is_single_session(db: DB, anchor: Anchor) -> bool:
    """True if all source turns of this anchor belong to one session."""
    count = await unique_session_count(db, anchor.source_turn_ids)
    return count <= 1


async def can_be_validated(db: DB, anchor: Anchor) -> bool:
    """Return whether an anchor is eligible for validated status.

    P4 M1 gate: anchor is eligible for "validated" status only if it spans
    multiple sessions. Single-session anchors get "tentative" at most.

    This helper only declares eligibility; downstream promotion logic
    (save_anchor / synthesis) is not yet wired to call this. M2 will add the
    integration.
    """
    return not await is_single_session(db, anchor)
