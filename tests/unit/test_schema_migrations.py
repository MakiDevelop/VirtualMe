"""Tests for inline schema migrations in src/virtualme/storage/db.py."""

import sys
from pathlib import Path

import aiosqlite

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from virtualme.storage.db import _apply_schema_migrations


async def _create_v041_anchors(db_path: str) -> None:
    """v0.4.1 anchors table -- WITHOUT source_question_ids."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("""
            CREATE TABLE anchors (
                id INTEGER PRIMARY KEY,
                interviewee_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                layer TEXT NOT NULL,
                content TEXT NOT NULL,
                source_turn_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                pii_tag TEXT
            )
        """)
        await conn.commit()


async def _create_v043_sessions(db_path: str) -> None:
    """sessions table -- WITHOUT current_question_id."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("""
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interviewee_id TEXT NOT NULL,
                week INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                energy_score INTEGER,
                notes TEXT,
                UNIQUE(interviewee_id, week)
            )
        """)
        await conn.commit()


async def _create_v042_anchors(db_path: str) -> None:
    """v0.4.2 anchors table -- WITH source_question_ids."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("""
            CREATE TABLE anchors (
                id INTEGER PRIMARY KEY,
                interviewee_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                layer TEXT NOT NULL,
                content TEXT NOT NULL,
                source_question_ids TEXT NOT NULL DEFAULT '[]',
                source_turn_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                pii_tag TEXT
            )
        """)
        await conn.commit()


async def _column_exists(db_path: str, table: str, column: str) -> bool:
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in await cursor.fetchall())


async def test_migration_applies_to_v041_db(tmp_path):
    db = tmp_path / "v041.db"
    await _create_v041_anchors(str(db))
    assert not await _column_exists(str(db), "anchors", "source_question_ids")

    async with aiosqlite.connect(str(db)) as conn:
        await _apply_schema_migrations(conn)
        await conn.commit()

    assert await _column_exists(str(db), "anchors", "source_question_ids")


async def test_migration_idempotent_on_v042_db(tmp_path):
    db = tmp_path / "v042.db"
    await _create_v042_anchors(str(db))

    async with aiosqlite.connect(str(db)) as conn:
        await _apply_schema_migrations(conn)
        await conn.commit()

    assert await _column_exists(str(db), "anchors", "source_question_ids")


async def test_migration_safe_run_twice(tmp_path):
    db = tmp_path / "twice.db"
    await _create_v041_anchors(str(db))

    async with aiosqlite.connect(str(db)) as conn:
        await _apply_schema_migrations(conn)
        await _apply_schema_migrations(conn)
        await conn.commit()

    assert await _column_exists(str(db), "anchors", "source_question_ids")


async def test_migration_no_anchors_table(tmp_path):
    db = tmp_path / "empty.db"
    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute("CREATE TABLE other (id INTEGER)")
        await conn.commit()
        await _apply_schema_migrations(conn)


async def test_migrated_column_default(tmp_path):
    db = tmp_path / "data.db"
    await _create_v041_anchors(str(db))

    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute(
            "INSERT INTO anchors (interviewee_id, dimension, layer, content) "
            "VALUES ('alice', 'SOUL', 'principle', 'honesty matters')"
        )
        await conn.commit()
        await _apply_schema_migrations(conn)
        cursor = await conn.execute(
            "SELECT source_question_ids FROM anchors WHERE interviewee_id='alice'"
        )
        row = await cursor.fetchone()
        await conn.commit()

    assert row[0] == "[]"


async def test_migration_adds_anchor_archive_columns(tmp_path):
    db = tmp_path / "archive-columns.db"
    await _create_v042_anchors(str(db))

    async with aiosqlite.connect(str(db)) as conn:
        await _apply_schema_migrations(conn)
        await conn.commit()

    assert await _column_exists(str(db), "anchors", "active")
    assert await _column_exists(str(db), "anchors", "archived_at")
    assert await _column_exists(str(db), "anchors", "archive_reason")


async def test_migration_adds_triple_archive_columns(tmp_path):
    db = tmp_path / "triple-archive-columns.db"
    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute("""
            CREATE TABLE persona_triples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interviewee_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                relation TEXT NOT NULL,
                object TEXT NOT NULL,
                source_turn_ids TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                embedding BLOB,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.commit()
        await _apply_schema_migrations(conn)
        await conn.commit()

    assert await _column_exists(str(db), "persona_triples", "active")
    assert await _column_exists(str(db), "persona_triples", "archived_at")
    assert await _column_exists(str(db), "persona_triples", "archive_reason")


async def test_migration_handles_duplicate_column_race(tmp_path):
    """Simulate race: column already added externally between PRAGMA and ALTER."""
    db = tmp_path / "race.db"
    await _create_v041_anchors(str(db))

    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute(
            "ALTER TABLE anchors "
            "ADD COLUMN source_question_ids TEXT NOT NULL DEFAULT '[]'"
        )
        await conn.commit()
        await _apply_schema_migrations(conn)
        await conn.commit()

    assert await _column_exists(str(db), "anchors", "source_question_ids")


async def test_migration_adds_current_question_id_to_sessions(tmp_path):
    db = tmp_path / "sessions.db"
    await _create_v043_sessions(str(db))
    assert not await _column_exists(str(db), "sessions", "current_question_id")

    async with aiosqlite.connect(str(db)) as conn:
        await _apply_schema_migrations(conn)
        await conn.commit()

    assert await _column_exists(str(db), "sessions", "current_question_id")


async def test_migration_creates_persona_download_tables(tmp_path):
    db = tmp_path / "download-tables.db"
    async with aiosqlite.connect(str(db)) as conn:
        await _apply_schema_migrations(conn)
        await conn.commit()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('persona_download_tokens', 'persona_download_logs')"
        )
        tables = {row[0] for row in await cursor.fetchall()}

    assert tables == {"persona_download_tokens", "persona_download_logs"}
