"""Unit tests for L1 TurnState assembly (read-only snapshot).

Covers:
- Basic construction from populated DB state
- restart path (fresh week-1 session, probe=0, candidates start from first)
- retalk path (current pinned to dimension's first question)
- light-greeting / resume path (current may be unset -> resolves to default)
- frozen immutability
- goal fallback vs explicit subject.goal
- candidate filtering (excludes asked)
"""

import tempfile
from pathlib import Path

import pytest

from virtualme.interview.question_selector import QuestionSelector, load_question_pool
from virtualme.interview.turn_state import (
    DEFAULT_GOAL,
    TurnState,
    build_turn_state,
)
from virtualme.storage.db import DB, Dimension, SubjectDomain


@pytest.fixture
def tmp_db_path() -> Path:
    """Temporary SQLite file for each test (auto-cleaned)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "virtualme-test.db"


@pytest.fixture
async def fresh_db(tmp_db_path: Path) -> DB:
    """Initialized DB with schema."""
    db = DB(str(tmp_db_path))
    await db.init()
    return db


@pytest.fixture
def selector() -> QuestionSelector:
    """Real question pool (from src/virtualme/data/question-pool.yaml)."""
    pool = load_question_pool()
    assert pool, "question pool must not be empty for tests"
    return QuestionSelector(pool)


async def _setup_minimal_session(
    db: DB,
    interviewee_id: str = "u-test-turnstate",
    week: int = 1,
    goal: str | None = None,
) -> tuple:
    """Create subject + session. Return (session, first_q_of_week)."""
    subject = await db.get_or_create_subject(
        interviewee_id, goal=goal, domain=SubjectDomain.HR_HRBP
    )
    session = await db.get_or_create_session(interviewee_id, week=week)
    # pick first question of the week as "current"
    first_q = QuestionSelector(load_question_pool()).question_pool.get(
        week, [None]
    )[0]
    if first_q:
        await db.set_current_question_id(session.id, first_q.id)
        await db.record_question_asked(interviewee_id, first_q.id, week)
    return session, first_q, subject


@pytest.mark.asyncio
async def test_build_basic_fields_populated(fresh_db: DB, selector: QuestionSelector):
    """Happy path: all core fields present and types correct."""
    session, current_q, _ = await _setup_minimal_session(fresh_db, week=1)

    # add a bit of history and one anchor
    await fresh_db.save_turn(session.id, "user", "我最近工作很忙")
    await fresh_db.save_turn(session.id, "assistant", "那你覺得忙在哪裡?")
    # fake anchor
    await fresh_db.save_anchor(
        "u-test-turnstate",
        Dimension.VOICE,
        "fact",
        "工作很忙",
        source_turn_ids=[1],
        source_question_ids=[current_q.id if current_q else "Q1"],
    )

    state = await build_turn_state(
        "u-test-turnstate", fresh_db, selector, session, adaptive=False
    )

    assert isinstance(state, TurnState)
    assert state.goal == DEFAULT_GOAL  # no explicit goal passed
    assert state.current_question.id == current_q.id if current_q else "STATE-OPEN"
    assert state.last_prompt_text is None or isinstance(state.last_prompt_text, str)
    assert isinstance(state.recent_history, list)
    assert len(state.recent_history) >= 2
    assert Dimension.VOICE in state.anchors_summary
    assert isinstance(state.coverage_gaps, dict)
    assert state.probe_count == 0
    assert isinstance(state.candidate_questions, list)
    assert len(state.candidate_questions) >= 1


@pytest.mark.asyncio
async def test_build_goal_from_subject(fresh_db: DB, selector: QuestionSelector):
    """Explicit subject.goal should override DEFAULT_GOAL."""
    session, _, _ = await _setup_minimal_session(
        fresh_db, goal="專門萃取工程師的技術決策模式"
    )

    state = await build_turn_state(
        "u-test-turnstate", fresh_db, selector, session, adaptive=False
    )
    assert state.goal == "專門萃取工程師的技術決策模式"


@pytest.mark.asyncio
async def test_build_restart_path(fresh_db: DB, selector: QuestionSelector):
    """After restart: new session week=1, first question, probe=0, candidates include first of week."""
    # simulate restart flow (see bot._handle_restart)
    session, first_q, _ = await _setup_minimal_session(fresh_db, week=1)

    state = await build_turn_state(
        "u-test-turnstate", fresh_db, selector, session, adaptive=False
    )

    assert state.current_question.week == 1
    assert state.probe_count == 0
    # at least the first of week 1 should be in candidates (or all if none excluded)
    ids = {q.id for q in state.candidate_questions}
    assert first_q.id in ids or len(state.candidate_questions) > 0


@pytest.mark.asyncio
async def test_build_retalk_path(fresh_db: DB, selector: QuestionSelector):
    """Retalk pins current to a dimension's first question; build reflects it."""
    session, _, _ = await _setup_minimal_session(fresh_db, week=2)

    # pick a dimension that has questions in the pool (VOICE or STATE usually does)
    target_dim = Dimension.VOICE
    dim_questions = [
        q for q in selector.question_pool.get(2, []) if q.dimension == target_dim
    ] or [q for qs in selector.question_pool.values() for q in qs if q.dimension == target_dim]
    if not dim_questions:
        dim_questions = [q for qs in selector.question_pool.values() for q in qs]

    target_q = dim_questions[0]
    await fresh_db.set_current_question_id(session.id, target_q.id)
    await fresh_db.record_question_asked("u-test-turnstate", target_q.id, 2)

    state = await build_turn_state(
        "u-test-turnstate", fresh_db, selector, session, adaptive=False
    )

    assert state.current_question.id == target_q.id
    assert state.current_question.dimension == target_q.dimension


@pytest.mark.asyncio
async def test_build_light_greeting_unset_current(fresh_db: DB, selector: QuestionSelector):
    """Light-greeting path before set_current: build still succeeds using default resolution."""
    # create session but do NOT set current_question_id
    session = await fresh_db.get_or_create_session("u-test-turnstate", week=1)

    state = await build_turn_state(
        "u-test-turnstate", fresh_db, selector, session, adaptive=False
    )

    # should resolve to some question (default of week 1)
    assert state.current_question is not None
    assert state.current_question.week == 1
    # probe may be 0, candidates non-empty
    assert state.probe_count >= 0
    assert len(state.candidate_questions) >= 1


@pytest.mark.asyncio
async def test_turn_state_is_frozen(fresh_db: DB, selector: QuestionSelector):
    """TurnState must be immutable (frozen pydantic model)."""
    session, _, _ = await _setup_minimal_session(fresh_db, week=1)
    state = await build_turn_state(
        "u-test-turnstate", fresh_db, selector, session, adaptive=False
    )

    with pytest.raises((AttributeError, TypeError, ValueError)):
        state.probe_count = 99  # frozen


@pytest.mark.asyncio
async def test_build_filters_candidates_by_asked(fresh_db: DB, selector: QuestionSelector):
    """candidate_questions should exclude questions with asked_count > 0 (except current edge)."""
    session, _first_q, _ = await _setup_minimal_session(fresh_db, week=1)

    # mark one more as asked
    all_q = [q for qs in selector.question_pool.values() for q in qs]
    if len(all_q) > 1:
        second = all_q[1]
        await fresh_db.record_question_asked("u-test-turnstate", second.id, 1)

    state = await build_turn_state(
        "u-test-turnstate", fresh_db, selector, session, adaptive=False
    )

    asked_ids = await fresh_db.load_asked_question_ids("u-test-turnstate")
    for cand in state.candidate_questions:
        # current may still be present; others should not be re-listed if asked
        if cand.id in asked_ids and cand.id != state.current_question.id:
            pytest.fail(f"asked question {cand.id} leaked into candidates")
