from virtualme.storage.db import DB


async def test_current_week_starts_at_one_for_new_interviewee(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    assert await db.get_current_week("u1") == 1


async def test_current_week_stays_on_one_for_active_session(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.get_or_create_session("u1", week=1)

    assert await db.get_current_week("u1") == 1


async def test_current_week_advances_after_completed_session(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    session = await db.get_or_create_session("u1", week=1)
    await db.mark_session_completed(session.id)

    assert await db.get_current_week("u1") == 2


async def test_current_week_caps_at_max_week(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    for week in range(1, 9):
        session = await db.get_or_create_session("u1", week=week)
        await db.mark_session_completed(session.id)

    assert await db.get_current_week("u1") == 8


async def test_current_week_uses_max_completed_week_even_with_gaps(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    for week in [1, 3]:
        session = await db.get_or_create_session("u1", week=week)
        await db.mark_session_completed(session.id)

    assert await db.get_current_week("u1") == 4


async def test_current_week_is_isolated_by_interviewee(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    session = await db.get_or_create_session("u1", week=1)
    await db.mark_session_completed(session.id)

    assert await db.get_current_week("u1") == 2
    assert await db.get_current_week("u2") == 1

