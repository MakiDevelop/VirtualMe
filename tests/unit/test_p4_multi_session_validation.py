"""P4 Multi-Session Validation hard gate -- Constitution v1.1 §P4.

Three categories:
1. unique_session_count / is_single_session unit tests
2. can_be_validated negative constraint
3. Gap-surfacing regression: save_anchor PRINCIPLE with 3 question_ids in
   single session creates triangulated=True, but can_be_validated=False
   (documents the M1->M2 gap)
"""

import pytest

from virtualme.snapshot.multi_session_validator import (
    can_be_validated,
    is_single_session,
    unique_session_count,
)
from virtualme.storage.db import DB, Dimension, Layer


async def _new_db(tmp_path) -> DB:
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    return db


# === Category 1: unique_session_count / is_single_session ===


@pytest.mark.asyncio
async def test_empty_turn_ids_returns_zero_sessions(tmp_path):
    db = await _new_db(tmp_path)
    assert await unique_session_count(db, []) == 0


@pytest.mark.asyncio
async def test_three_turns_same_session_count_one(tmp_path):
    db = await _new_db(tmp_path)
    sess = await db.get_or_create_session("u1", 1)
    t1 = await db.save_turn(sess.id, "user", "msg1")
    t2 = await db.save_turn(sess.id, "user", "msg2")
    t3 = await db.save_turn(sess.id, "user", "msg3")
    count = await unique_session_count(db, [t1.id, t2.id, t3.id])
    assert count == 1


@pytest.mark.asyncio
async def test_turns_across_two_sessions_count_two(tmp_path):
    db = await _new_db(tmp_path)
    s1 = await db.get_or_create_session("u1", 1)
    s2 = await db.get_or_create_session("u1", 2)
    t1 = await db.save_turn(s1.id, "user", "a")
    t2 = await db.save_turn(s2.id, "user", "b")
    assert await unique_session_count(db, [t1.id, t2.id]) == 2


@pytest.mark.asyncio
async def test_is_single_session_for_same_session(tmp_path):
    db = await _new_db(tmp_path)
    sess = await db.get_or_create_session("u1", 1)
    t1 = await db.save_turn(sess.id, "user", "a")
    t2 = await db.save_turn(sess.id, "user", "b")
    anchor = await db.save_anchor(
        "u1", Dimension.SOUL, Layer.PRINCIPLE, "c", [t1.id, t2.id], ["Q1", "Q2"]
    )
    assert await is_single_session(db, anchor) is True


@pytest.mark.asyncio
async def test_is_single_session_for_cross_session(tmp_path):
    db = await _new_db(tmp_path)
    s1 = await db.get_or_create_session("u1", 1)
    s2 = await db.get_or_create_session("u1", 2)
    t1 = await db.save_turn(s1.id, "user", "a")
    t2 = await db.save_turn(s2.id, "user", "b")
    anchor = await db.save_anchor(
        "u1", Dimension.SOUL, Layer.PRINCIPLE, "c", [t1.id, t2.id], ["Q1", "Q2"]
    )
    assert await is_single_session(db, anchor) is False


# === Category 2: can_be_validated ===


@pytest.mark.asyncio
async def test_single_session_anchor_cannot_be_validated(tmp_path):
    db = await _new_db(tmp_path)
    sess = await db.get_or_create_session("u1", 1)
    t = await db.save_turn(sess.id, "user", "msg")
    anchor = await db.save_anchor(
        "u1", Dimension.SOUL, Layer.PRINCIPLE, "x", [t.id], ["Q1"]
    )
    assert await can_be_validated(db, anchor) is False


@pytest.mark.asyncio
async def test_cross_session_anchor_can_be_validated(tmp_path):
    db = await _new_db(tmp_path)
    s1 = await db.get_or_create_session("u1", 1)
    s2 = await db.get_or_create_session("u1", 2)
    t1 = await db.save_turn(s1.id, "user", "a")
    t2 = await db.save_turn(s2.id, "user", "b")
    anchor = await db.save_anchor(
        "u1", Dimension.SOUL, Layer.PRINCIPLE, "c", [t1.id, t2.id], ["Q1", "Q2"]
    )
    assert await can_be_validated(db, anchor) is True


# === Category 3: Gap-surfacing regression ===


@pytest.mark.asyncio
async def test_single_session_triangulated_anchor_still_cannot_validated(tmp_path):
    """P4 M1 contract: triangulated != validated for same-session evidence."""
    db = await _new_db(tmp_path)
    sess = await db.get_or_create_session("u1", 1)
    t1 = await db.save_turn(sess.id, "user", "a")
    t2 = await db.save_turn(sess.id, "user", "b")
    t3 = await db.save_turn(sess.id, "user", "c")
    anchor = await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "I value direct truth over peace",
        [t1.id, t2.id, t3.id],
        ["Q1", "Q2", "Q3"],
    )
    assert anchor.triangulated is True
    assert await can_be_validated(db, anchor) is False
