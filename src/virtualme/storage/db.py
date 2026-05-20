from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import aiosqlite
from pydantic import BaseModel

if TYPE_CHECKING:
    from virtualme.interview.pii import Redaction

T = TypeVar("T")


class Dimension(StrEnum):
    SOUL = "SOUL"
    VOICE = "VOICE"
    SKILL = "SKILL"
    PEOPLE = "PEOPLE"
    HISTORY = "HISTORY"
    JOURNAL = "JOURNAL"
    BOUNDARIES = "BOUNDARIES"
    STATE = "STATE"


class Layer(StrEnum):
    FACT = "fact"
    PATTERN = "pattern"
    PRINCIPLE = "principle"


class SubjectDomain(StrEnum):
    HR_HRBP = "hr-hrbp"
    SALES = "sales"
    ENGINEER = "engineer"
    PM = "pm"
    TEACHER = "teacher"
    CONSULTANT = "consultant"
    OTHER = "other"
    UNSPECIFIED = "unspecified"


class SubjectStatus(StrEnum):
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    DEPLOYED = "deployed"
    EVALUATED = "evaluated"
    DONE = "done"


class Verdict(StrEnum):
    SHIP_READY = "ship-ready"
    NEEDS_WORK = "needs-work"
    OVERFIT_WARNING = "overfit-warning"


class Session(BaseModel):
    id: int
    interviewee_id: str
    week: int
    status: str = "active"
    energy_score: int | None = None


class Turn(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    content_hash: str


class Anchor(BaseModel):
    id: int | None = None
    interviewee_id: str
    dimension: Dimension
    layer: Layer
    content: str
    triangulated: bool = False
    source_turn_ids: list[int] = []
    source_question_ids: list[str] = []


class Principle(BaseModel):
    dimension: Dimension
    content: str
    source_turn_ids: list[int]


class Question(BaseModel):
    id: str
    week: int
    dimension: Dimension
    text: str
    rationale_probe: str | None = None
    energy_tax: str = "mid"


class Subject(BaseModel):
    interviewee_id: str
    display_name: str | None = None
    domain: SubjectDomain = SubjectDomain.UNSPECIFIED
    goal: str | None = None
    status: SubjectStatus = SubjectStatus.EXTRACTING
    created_at: str | None = None
    updated_at: str | None = None


class ChecklistItem(BaseModel):
    interviewee_id: str
    item_key: str
    label: str
    done: bool = False
    note: str | None = None
    updated_at: str | None = None


POC_CHECKLIST_TEMPLATE: list[tuple[str, str]] = [
    ("extraction_sessions", "完成萃取對話（adaptive 模式）"),  # noqa: RUF001
    ("voice_boundaries_coverage", "VOICE / BOUNDARIES 覆蓋達標"),
    ("persona_exported", "persona 匯出"),
    ("responder_deployed", "responder 部署"),
    ("scorecard_pass", "12 則 scorecard：voice+acceptability ≥ 8/12"),  # noqa: RUF001
    ("correctness_clean", "correctness 零「自信講錯」嚴重案例"),
    ("go_nogo_recorded", "go / no-go 結論已記錄"),
]


def _schema_path() -> Path:
    return Path(__file__).with_name("schema.sql")


async def _apply_schema_migrations(conn: aiosqlite.Connection) -> None:
    """Idempotent inline schema migrations.

    Aligned with memory-hall's pattern: read existing columns via
    PRAGMA table_info, then apply any migrations whose target column
    is missing. Race-safe via try/except on duplicate column.

    Runs on every init_db() call. Adding a new migration = append a
    tuple to the relevant table's list below.

    Per memory-hall convention, migrations/*.sql files in repo root
    are human-readable documentation, NOT executed by this function.
    """
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
    )
    if await cursor.fetchone():
        cursor = await conn.execute("PRAGMA table_info(sessions)")
        existing_session_columns = {row[1] for row in await cursor.fetchall()}

        session_migrations: list[tuple[str, str]] = [
            (
                "current_question_id",
                "ALTER TABLE sessions ADD COLUMN current_question_id TEXT",
            ),
        ]

        for column_name, sql in session_migrations:
            if column_name in existing_session_columns:
                continue
            try:
                await conn.execute(sql)
            except aiosqlite.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='question_state'"
    )
    if await cursor.fetchone():
        cursor = await conn.execute("PRAGMA table_info(question_state)")
        existing_question_state_columns = {row[1] for row in await cursor.fetchall()}

        question_state_migrations: list[tuple[str, str]] = [
            (
                "probe_count",
                "ALTER TABLE question_state ADD COLUMN probe_count INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "non_answer_count",
                "ALTER TABLE question_state "
                "ADD COLUMN non_answer_count INTEGER NOT NULL DEFAULT 0",
            ),
        ]

        for column_name, sql in question_state_migrations:
            if column_name in existing_question_state_columns:
                continue
            try:
                await conn.execute(sql)
            except aiosqlite.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    # Anchors table migrations
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='anchors'"
    )
    if await cursor.fetchone():
        cursor = await conn.execute("PRAGMA table_info(anchors)")
        existing_anchor_columns = {row[1] for row in await cursor.fetchall()}

        anchor_migrations: list[tuple[str, str]] = [
            (
                "source_question_ids",
                "ALTER TABLE anchors "
                "ADD COLUMN source_question_ids TEXT NOT NULL DEFAULT '[]'",
            ),
            (
                "active",
                "ALTER TABLE anchors ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
            ),
            (
                "archived_at",
                "ALTER TABLE anchors ADD COLUMN archived_at TEXT",
            ),
            (
                "archive_reason",
                "ALTER TABLE anchors ADD COLUMN archive_reason TEXT",
            ),
            (
                "model",
                "ALTER TABLE anchors ADD COLUMN model TEXT",
            ),
            # v0.5+ anchor migrations append here
        ]

        for column_name, sql in anchor_migrations:
            if column_name in existing_anchor_columns:
                continue
            try:
                await conn.execute(sql)
            except aiosqlite.OperationalError as exc:
                # Race condition: another process added the column between
                # our PRAGMA check and ALTER. Treat as already-migrated.
                if "duplicate column" not in str(exc).lower():
                    raise

    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='persona_triples'"
    )
    if await cursor.fetchone():
        cursor = await conn.execute("PRAGMA table_info(persona_triples)")
        existing_triple_columns = {row[1] for row in await cursor.fetchall()}

        triple_migrations: list[tuple[str, str]] = [
            (
                "active",
                "ALTER TABLE persona_triples ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
            ),
            (
                "archived_at",
                "ALTER TABLE persona_triples ADD COLUMN archived_at TEXT",
            ),
            (
                "archive_reason",
                "ALTER TABLE persona_triples ADD COLUMN archive_reason TEXT",
            ),
        ]

        for column_name, sql in triple_migrations:
            if column_name in existing_triple_columns:
                continue
            try:
                await conn.execute(sql)
            except aiosqlite.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transport_events (
            event_id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            interviewee_id TEXT,
            message_id TEXT,
            status TEXT NOT NULL DEFAULT 'processing',
            error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS persona_download_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            interviewee_id TEXT NOT NULL,
            zip_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            download_count INTEGER NOT NULL DEFAULT 0,
            last_downloaded_at TEXT
        )
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_persona_download_tokens_expires_at
        ON persona_download_tokens(expires_at)
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS persona_download_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interviewee_id TEXT,
            token_hash TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            success INTEGER NOT NULL,
            failure_reason TEXT,
            zip_path TEXT
        )
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_persona_download_logs_token_hash
        ON persona_download_logs(token_hash)
        """
    )


async def init_db(path: str) -> None:
    """Initialize SQLite DB: pragmas, schema, migrations."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as conn:
        # Pragma defaults aligned with memory-hall best practices.
        # WAL improves concurrent reader throughput.
        # synchronous=NORMAL trades crash durability for write speed
        # (acceptable for personal-scale local DB).
        # busy_timeout avoids "database is locked" on transient contention.
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        await conn.execute("PRAGMA busy_timeout=5000;")

        await conn.executescript(_schema_path().read_text())
        await _apply_schema_migrations(conn)
        await conn.commit()


class DB:
    def __init__(self, path: str):
        self.path = path

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        """Open a connection with memhall-aligned per-connection pragmas.

        Per Gemini v3 pivot review: `synchronous=NORMAL` and `busy_timeout`
        are per-connection settings in SQLite, NOT persistent. Applying them
        only in init_db() leaves all subsequent writes running with
        synchronous=FULL (slower) and busy_timeout=0 (lock-prone). This
        helper ensures every DB method gets the right pragmas.

        WAL mode is set once via init_db() — it persists in the DB file.
        """
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute("PRAGMA synchronous=NORMAL;")
            await conn.execute("PRAGMA busy_timeout=5000;")
            yield conn

    async def init(self) -> None:
        await init_db(self.path)

    async def get_or_create_subject(
        self,
        interviewee_id: str,
        domain: SubjectDomain = SubjectDomain.UNSPECIFIED,
        display_name: str | None = None,
        goal: str | None = None,
    ) -> Subject:
        await self.init()
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute(
                """
                INSERT OR IGNORE INTO subjects(
                    interviewee_id, display_name, domain, goal
                )
                VALUES (?, ?, ?, ?)
                """,
                (interviewee_id, display_name, domain.value, goal),
            )
            await conn.commit()
            row = await (
                await conn.execute(
                    "SELECT * FROM subjects WHERE interviewee_id = ?",
                    (interviewee_id,),
                )
            ).fetchone()
        return _subject_from_row(row)

    async def get_subject(self, interviewee_id: str) -> Subject | None:
        await self.init()
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = await (
                await conn.execute(
                    "SELECT * FROM subjects WHERE interviewee_id = ?",
                    (interviewee_id,),
                )
            ).fetchone()
        return _subject_from_row(row) if row else None

    async def update_subject(
        self,
        interviewee_id: str,
        *,
        domain: SubjectDomain | None = None,
        goal: str | None = None,
        display_name: str | None = None,
        status: SubjectStatus | None = None,
    ) -> Subject:
        await self.init()
        updates: list[str] = []
        params: list[str] = []
        if domain is not None:
            updates.append("domain = ?")
            params.append(domain.value)
        if goal is not None:
            updates.append("goal = ?")
            params.append(goal)
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if status is not None:
            updates.append("status = ?")
            params.append(status.value)

        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            if updates:
                params.append(interviewee_id)
                await conn.execute(
                    f"""
                    UPDATE subjects
                    SET {", ".join(updates)},
                        updated_at = CURRENT_TIMESTAMP
                    WHERE interviewee_id = ?
                    """,
                    params,
                )
                await conn.commit()
            row = await (
                await conn.execute(
                    "SELECT * FROM subjects WHERE interviewee_id = ?",
                    (interviewee_id,),
                )
            ).fetchone()
        if row is None:
            raise ValueError(f"subject not found: {interviewee_id}")
        return _subject_from_row(row)

    async def seed_poc_checklist(self, interviewee_id: str) -> list[ChecklistItem]:
        await self.init()
        async with self._connect() as conn:
            await conn.executemany(
                """
                INSERT OR IGNORE INTO checklist_items(interviewee_id, item_key, label)
                VALUES (?, ?, ?)
                """,
                [
                    (interviewee_id, item_key, label)
                    for item_key, label in POC_CHECKLIST_TEMPLATE
                ],
            )
            await conn.commit()
        return await self.get_checklist(interviewee_id)

    async def get_checklist(self, interviewee_id: str) -> list[ChecklistItem]:
        await self.init()
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM checklist_items WHERE interviewee_id = ?",
                (interviewee_id,),
            )
            rows = await cur.fetchall()

        by_key = {row["item_key"]: row for row in rows}
        return [
            _checklist_item_from_row(by_key[item_key])
            for item_key, _label in POC_CHECKLIST_TEMPLATE
            if item_key in by_key
        ]

    async def set_checklist_item(
        self,
        interviewee_id: str,
        item_key: str,
        done: bool,
        note: str | None = None,
    ) -> ChecklistItem:
        await self.init()
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            if note is None:
                await conn.execute(
                    """
                    UPDATE checklist_items
                    SET done = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE interviewee_id = ? AND item_key = ?
                    """,
                    (int(done), interviewee_id, item_key),
                )
            else:
                await conn.execute(
                    """
                    UPDATE checklist_items
                    SET done = ?,
                        note = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE interviewee_id = ? AND item_key = ?
                    """,
                    (int(done), note, interviewee_id, item_key),
                )
            await conn.commit()
            row = await (
                await conn.execute(
                    """
                    SELECT * FROM checklist_items
                    WHERE interviewee_id = ? AND item_key = ?
                    """,
                    (interviewee_id, item_key),
                )
            ).fetchone()

        if row is None:
            raise ValueError(f"checklist item not found: {interviewee_id}/{item_key}")
        return _checklist_item_from_row(row)

    async def get_or_create_session(self, interviewee_id: str, week: int) -> Session:
        await self.init()
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute(
                "INSERT OR IGNORE INTO sessions(interviewee_id, week) VALUES (?, ?)",
                (interviewee_id, week),
            )
            await conn.commit()
            row = await (
                await conn.execute(
                    "SELECT * FROM sessions WHERE interviewee_id = ? AND week = ?",
                    (interviewee_id, week),
                )
            ).fetchone()
        return Session(**dict(row))

    async def get_current_week(self, interviewee_id: str, max_week: int = 8) -> int:
        await self.init()
        async with self._connect() as conn:
            row = await (
                await conn.execute(
                    """
                    SELECT MAX(week) AS max_completed_week
                    FROM sessions
                    WHERE interviewee_id = ?
                      AND status = 'completed'
                    """,
                    (interviewee_id,),
                )
            ).fetchone()
        completed_week = row[0] if row and row[0] is not None else 0
        return max(1, min(int(completed_week) + 1, max_week))

    async def get_current_question_id(self, session_id: int) -> str | None:
        async with self._connect() as conn:
            row = await (
                await conn.execute(
                    "SELECT current_question_id FROM sessions WHERE id = ?",
                    (session_id,),
                )
            ).fetchone()
        return str(row[0]) if row and row[0] else None

    async def set_current_question_id(self, session_id: int, question_id: str) -> None:
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE sessions SET current_question_id = ? WHERE id = ?",
                (question_id, session_id),
            )
            await conn.commit()

    async def restart_dimension(
        self,
        interviewee_id: str,
        dimension: Dimension,
        question_ids: list[str],
        *,
        reason: str = "dimension_restart",
    ) -> int:
        """Archive a dimension's active anchors and reset its question progress.

        This is intentionally a soft archive: old anchors remain in SQLite with
        provenance, but active persona context and exports start fresh for the
        selected dimension.
        """
        async with self._connect() as conn:
            cur = await conn.execute(
                """
                UPDATE anchors
                SET active = 0,
                    archived_at = CURRENT_TIMESTAMP,
                    archive_reason = ?
                WHERE interviewee_id = ?
                  AND dimension = ?
                  AND active = 1
                """,
                (reason, interviewee_id, dimension.value),
            )
            if question_ids:
                placeholders = ", ".join("?" for _ in question_ids)
                await conn.execute(
                    f"""
                    DELETE FROM question_state
                    WHERE interviewee_id = ?
                      AND question_id IN ({placeholders})
                    """,
                    [interviewee_id, *question_ids],
                )
            await conn.commit()
        return cur.rowcount

    async def restart_interview(
        self, interviewee_id: str, *, reason: str = "interview_restart"
    ) -> dict[str, int]:
        """Soft-archive active interview memory and reset progress for a fresh run."""
        async with self._connect() as conn:
            anchor_cur = await conn.execute(
                """
                UPDATE anchors
                SET active = 0,
                    archived_at = CURRENT_TIMESTAMP,
                    archive_reason = ?
                WHERE interviewee_id = ?
                  AND active = 1
                """,
                (reason, interviewee_id),
            )
            triple_cur = await conn.execute(
                """
                UPDATE persona_triples
                SET active = 0,
                    archived_at = CURRENT_TIMESTAMP,
                    archive_reason = ?
                WHERE interviewee_id = ?
                  AND active = 1
                """,
                (reason, interviewee_id),
            )
            session_cur = await conn.execute(
                """
                UPDATE sessions
                SET ended_at = CURRENT_TIMESTAMP,
                    status = 'archived',
                    current_question_id = NULL,
                    notes = COALESCE(notes || char(10), '') ||
                        'archived_reason=' || ? || '; original_week=' || week,
                    week = -id
                WHERE interviewee_id = ?
                """,
                (reason, interviewee_id),
            )
            await conn.execute(
                "DELETE FROM question_state WHERE interviewee_id = ?",
                (interviewee_id,),
            )
            await conn.commit()
        return {
            "anchors": anchor_cur.rowcount,
            "triples": triple_cur.rowcount,
            "sessions": session_cur.rowcount,
        }

    async def claim_transport_event(
        self,
        event_id: str,
        platform: str,
        interviewee_id: str | None = None,
        message_id: str | None = None,
    ) -> bool:
        """Return True only for the first delivery of a transport event.

        LINE retries webhooks when the HTTP response is not fast enough. The
        event/message id belongs at the transport boundary, not in turn storage,
        so duplicate deliveries are claimed here before any interview state is
        mutated.
        """
        async with self._connect() as conn:
            cur = await conn.execute(
                """
                INSERT OR IGNORE INTO transport_events(
                    event_id, platform, interviewee_id, message_id
                )
                VALUES (?, ?, ?, ?)
                """,
                (event_id, platform, interviewee_id, message_id),
            )
            await conn.commit()
        return cur.rowcount == 1

    async def mark_transport_event_done(self, event_id: str) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                UPDATE transport_events
                SET status = 'done',
                    error = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                """,
                (event_id,),
            )
            await conn.commit()

    async def mark_transport_event_failed(self, event_id: str, error: str) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                UPDATE transport_events
                SET status = 'failed',
                    error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                """,
                (error[:500], event_id),
            )
            await conn.commit()

    async def record_question_asked(
        self, interviewee_id: str, question_id: str, week: int
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO question_state(
                    interviewee_id, question_id, week, asked_count, last_asked_at
                )
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(interviewee_id, question_id)
                DO UPDATE SET
                    asked_count = asked_count + 1,
                    last_asked_at = CURRENT_TIMESTAMP,
                    week = excluded.week
                """,
                (interviewee_id, question_id, week),
            )
            await conn.commit()

    async def record_question_answered(
        self, interviewee_id: str, question_id: str, week: int, depth: str
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO question_state(
                    interviewee_id, question_id, week, asked_count, answered_depth
                )
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(interviewee_id, question_id)
                DO UPDATE SET
                    answered_depth = excluded.answered_depth,
                    non_answer_count = 0
                """,
                (interviewee_id, question_id, week, depth),
            )
            await conn.commit()

    async def get_probe_count(self, interviewee_id: str, question_id: str) -> int:
        async with self._connect() as conn:
            row = await (
                await conn.execute(
                    """
                    SELECT probe_count
                    FROM question_state
                    WHERE interviewee_id = ? AND question_id = ?
                    """,
                    (interviewee_id, question_id),
                )
            ).fetchone()
        return int(row[0]) if row else 0

    async def record_question_probe(
        self, interviewee_id: str, question_id: str, week: int
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO question_state(
                    interviewee_id, question_id, week, asked_count, probe_count
                )
                VALUES (?, ?, ?, 0, 1)
                ON CONFLICT(interviewee_id, question_id)
                DO UPDATE SET
                    probe_count = probe_count + 1,
                    week = excluded.week
                """,
                (interviewee_id, question_id, week),
            )
            await conn.commit()

    async def record_question_non_answer(
        self, interviewee_id: str, question_id: str, week: int
    ) -> int:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO question_state(
                    interviewee_id, question_id, week, asked_count, non_answer_count
                )
                VALUES (?, ?, ?, 0, 1)
                ON CONFLICT(interviewee_id, question_id)
                DO UPDATE SET
                    non_answer_count = non_answer_count + 1,
                    week = excluded.week
                """,
                (interviewee_id, question_id, week),
            )
            row = await (
                await conn.execute(
                    """
                    SELECT non_answer_count
                    FROM question_state
                    WHERE interviewee_id = ? AND question_id = ?
                    """,
                    (interviewee_id, question_id),
                )
            ).fetchone()
            await conn.commit()
        return int(row[0]) if row else 0

    async def reset_question_non_answer(
        self, interviewee_id: str, question_id: str
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                UPDATE question_state
                SET non_answer_count = 0
                WHERE interviewee_id = ? AND question_id = ?
                """,
                (interviewee_id, question_id),
            )
            await conn.commit()

    async def load_asked_question_ids(self, interviewee_id: str) -> set[str]:
        async with self._connect() as conn:
            cur = await conn.execute(
                "SELECT question_id FROM question_state "
                "WHERE interviewee_id = ? AND asked_count > 0",
                (interviewee_id,),
            )
            rows = await cur.fetchall()
        return {row[0] for row in rows}

    async def save_turn(self, session_id: int, role: str, content: str) -> Turn:
        # Turns are an append-only event log: the autoincrement id is the turn identity.
        # content_hash carries a per-turn nonce so repeated answers are not folded by
        # the UNIQUE constraint. Transport-level idempotency belongs in the webhook
        # layer using the platform message id, not here via content hashing.
        digest = hashlib.sha256(
            f"{session_id}:{role}:{content}:{time.time_ns()}".encode()
        ).hexdigest()
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                INSERT INTO turns(session_id, role, content, content_hash)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, digest),
            )
            await conn.commit()
            row = await (
                await conn.execute("SELECT * FROM turns WHERE id = ?", (cur.lastrowid,))
            ).fetchone()
        return Turn(**dict(row))

    async def get_last_assistant_content(self, session_id: int) -> str | None:
        async with self._connect() as conn:
            row = await (
                await conn.execute(
                    """
                    SELECT content FROM turns
                    WHERE session_id = ? AND role = 'assistant'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
            ).fetchone()
        return str(row[0]) if row else None

    async def save_redactions(self, turn_id: int, redactions: list[Redaction]) -> None:
        if not redactions:
            return
        async with self._connect() as conn:
            await conn.executemany(
                """
                INSERT INTO redactions(
                    turn_id, category, original, replacement, span_start, span_end
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        turn_id,
                        redaction.category,
                        redaction.original,
                        redaction.replacement,
                        redaction.span[0],
                        redaction.span[1],
                    )
                    for redaction in redactions
                ],
            )
            await conn.commit()

    async def save_anchor(
        self,
        interviewee_id: str,
        dimension: Dimension,
        layer: Layer,
        content: str,
        source_turn_ids: list[int],
        source_question_ids: list[str] | None = None,
        model: str | None = None,
    ) -> Anchor:
        turn_ids = _dedupe_preserve_order(source_turn_ids)
        question_ids = _dedupe_preserve_order(
            source_question_ids if source_question_ids is not None else []
        )
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            if layer == Layer.PRINCIPLE:
                existing = await self._find_matching_principle_anchor(
                    conn, interviewee_id, dimension, content
                )
                if existing is not None:
                    return await self._merge_anchor_sources(
                        conn, existing, source_turn_ids, question_ids
                    )
            triangulated = len(set(question_ids)) >= 3 if layer == Layer.PRINCIPLE else False
            cur = await conn.execute(
                """
                INSERT INTO anchors(
                    interviewee_id, dimension, layer, content,
                    triangulated, source_turn_ids, source_question_ids, model
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interviewee_id,
                    dimension,
                    layer,
                    content,
                    int(triangulated),
                    json.dumps(turn_ids),
                    json.dumps(question_ids),
                    model,
                ),
            )
            await conn.commit()
            anchor_id = cur.lastrowid
        return Anchor(
            id=anchor_id,
            interviewee_id=interviewee_id,
            dimension=dimension,
            layer=layer,
            content=content,
            triangulated=triangulated,
            source_turn_ids=turn_ids,
            source_question_ids=question_ids,
        )

    async def _find_matching_principle_anchor(
        self,
        conn: aiosqlite.Connection,
        interviewee_id: str,
        dimension: Dimension,
        content: str,
    ) -> aiosqlite.Row | None:
        cur = await conn.execute(
            """
            SELECT * FROM anchors
            WHERE interviewee_id = ?
              AND dimension = ?
              AND layer = ?
              AND active = 1
            ORDER BY created_at
            """,
            (interviewee_id, dimension, Layer.PRINCIPLE),
        )
        for row in await cur.fetchall():
            if _anchor_content_matches(content, row["content"]):
                return row
        return None

    async def _merge_anchor_sources(
        self,
        conn: aiosqlite.Connection,
        row: aiosqlite.Row,
        source_turn_ids: list[int],
        source_question_ids: list[str],
    ) -> Anchor:
        merged_turn_ids = _dedupe_preserve_order(
            json.loads(row["source_turn_ids"]) + source_turn_ids
        )
        merged_question_ids = _dedupe_preserve_order(
            json.loads(row["source_question_ids"]) + source_question_ids
        )
        triangulated = bool(row["triangulated"]) or len(set(merged_question_ids)) >= 3
        await conn.execute(
            """
            UPDATE anchors
            SET source_turn_ids = ?,
                source_question_ids = ?,
                triangulated = ?
            WHERE id = ?
            """,
            (
                json.dumps(merged_turn_ids),
                json.dumps(merged_question_ids),
                int(triangulated),
                row["id"],
            ),
        )
        await conn.commit()
        return Anchor(
            id=row["id"],
            interviewee_id=row["interviewee_id"],
            dimension=Dimension(row["dimension"]),
            layer=Layer(row["layer"]),
            content=row["content"],
            triangulated=triangulated,
            source_turn_ids=merged_turn_ids,
            source_question_ids=merged_question_ids,
        )

    async def save_triple(self, triple) -> None:
        from virtualme.interview.triples import PersonaTriple

        parsed = triple if isinstance(triple, PersonaTriple) else PersonaTriple(**triple)
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO persona_triples(
                    interviewee_id, subject, relation, object, source_turn_ids, confidence
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    parsed.interviewee_id,
                    parsed.subject,
                    parsed.relation,
                    parsed.object,
                    json.dumps(parsed.source_turn_ids),
                    parsed.confidence,
                ),
            )
            await conn.commit()

    async def save_blind_test(
        self,
        interviewee_id: str,
        week: int,
        correctness_per_item: dict[str, bool],
        overall_accuracy: float,
        verdict: Verdict,
        weakest_dimension: str | None = None,
        recommended_action: str | None = None,
    ) -> int:
        async with self._connect() as conn:
            cur = await conn.execute(
                """
                INSERT INTO blind_tests(
                    interviewee_id, week, correctness_per_item, overall_accuracy,
                    verdict, weakest_dimension, recommended_action
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interviewee_id,
                    week,
                    json.dumps(correctness_per_item),
                    overall_accuracy,
                    verdict,
                    weakest_dimension,
                    recommended_action,
                ),
            )
            await conn.commit()
        return int(cur.lastrowid)

    async def load_triples(self, interviewee_id: str, *, active_only: bool = True):
        from virtualme.interview.triples import PersonaTriple

        active_clause = "AND active = 1" if active_only else ""
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM persona_triples "
                f"WHERE interviewee_id = ? {active_clause} ORDER BY created_at",
                (interviewee_id,),
            )
            rows = await cur.fetchall()
        return [
            PersonaTriple(
                id=row["id"],
                interviewee_id=row["interviewee_id"],
                subject=row["subject"],
                relation=row["relation"],
                object=row["object"],
                source_turn_ids=json.loads(row["source_turn_ids"]),
                confidence=row["confidence"],
            )
            for row in rows
        ]

    async def update_triple_embedding(self, triple_id: int, embedding: bytes) -> None:
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE persona_triples SET embedding = ? WHERE id = ?",
                (embedding, triple_id),
            )
            await conn.commit()

    async def mark_triangulated(self, anchor_id: int) -> None:
        async with self._connect() as conn:
            await conn.execute("UPDATE anchors SET triangulated = 1 WHERE id = ?", (anchor_id,))
            await conn.commit()

    async def load_anchors_summary(self, interviewee_id: str) -> dict[Dimension, list[Anchor]]:
        summary: dict[Dimension, list[Anchor]] = {dimension: [] for dimension in Dimension}
        for row in await self._fetch_anchors(interviewee_id):
            anchor = _anchor_from_row(row)
            summary[anchor.dimension].append(anchor)
        return summary

    async def load_triangulated(self, interviewee_id: str) -> list[Principle]:
        rows = await self._fetch_anchors(interviewee_id, triangulated=True)
        return [
            Principle(
                dimension=Dimension(row["dimension"]),
                content=row["content"],
                source_turn_ids=json.loads(row["source_turn_ids"]),
            )
            for row in rows
        ]

    async def compute_coverage_gap(self, interviewee_id: str) -> dict[Dimension, float]:
        summary = await self.load_anchors_summary(interviewee_id)
        max_count = max((len(items) for items in summary.values()), default=0) or 1
        return {dimension: 1.0 - (len(items) / max_count) for dimension, items in summary.items()}

    async def count_turns(self, session_id: int) -> int:
        async with self._connect() as conn:
            row = await (
                await conn.execute("SELECT COUNT(*) AS count FROM turns WHERE session_id = ?", (session_id,))
            ).fetchone()
        return int(row[0])

    async def load_recent_turns(self, session_id: int, limit: int = 10) -> list[Turn]:
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT * FROM turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = await cur.fetchall()
        return [Turn(**dict(row)) for row in reversed(rows)]

    async def load_session_turns(self, session_id: int) -> list[Turn]:
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
            rows = await cur.fetchall()
        return [Turn(**dict(row)) for row in rows]

    async def mark_session_completed(self, session_id: int) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                UPDATE sessions
                SET ended_at = CURRENT_TIMESTAMP, status = 'completed'
                WHERE id = ?
                """,
                (session_id,),
            )
            await conn.commit()

    async def load_stale_active_sessions(self, threshold_minutes: int = 30) -> list[Session]:
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT sessions.*
                FROM sessions
                JOIN turns ON turns.session_id = sessions.id
                WHERE sessions.status = 'active'
                GROUP BY sessions.id
                HAVING MAX(turns.ts) <= datetime('now', ?)
                """,
                (f"-{threshold_minutes} minutes",),
            )
            rows = await cur.fetchall()
        return [Session(**dict(row)) for row in rows]

    async def _fetch_anchors(
        self,
        interviewee_id: str,
        triangulated: bool | None = None,
        *,
        active_only: bool = True,
    ):
        clause = "AND triangulated = ?" if triangulated is not None else ""
        active_clause = "AND active = 1" if active_only else ""
        params = (
            (interviewee_id, int(triangulated))
            if triangulated is not None
            else (interviewee_id,)
        )
        async with self._connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM anchors "
                f"WHERE interviewee_id = ? {clause} {active_clause} "
                "ORDER BY created_at",
                params,
            )
            return await cur.fetchall()


def _anchor_from_row(row: aiosqlite.Row) -> Anchor:
    row_keys = set(row.keys())
    source_question_ids_raw = (
        row["source_question_ids"] if "source_question_ids" in row_keys else "[]"
    )
    return Anchor(
        id=row["id"],
        interviewee_id=row["interviewee_id"],
        dimension=Dimension(row["dimension"]),
        layer=Layer(row["layer"]),
        content=row["content"],
        triangulated=bool(row["triangulated"]),
        source_turn_ids=json.loads(row["source_turn_ids"]),
        source_question_ids=json.loads(source_question_ids_raw),
    )


def _subject_from_row(row: aiosqlite.Row) -> Subject:
    return Subject(
        interviewee_id=row["interviewee_id"],
        display_name=row["display_name"],
        domain=SubjectDomain(row["domain"]),
        goal=row["goal"],
        status=SubjectStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _checklist_item_from_row(row: aiosqlite.Row) -> ChecklistItem:
    return ChecklistItem(
        interviewee_id=row["interviewee_id"],
        item_key=row["item_key"],
        label=row["label"],
        done=bool(row["done"]),
        note=row["note"],
        updated_at=row["updated_at"],
    )


_ANCHOR_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "best",
    "for",
    "is",
    "matter",
    "matters",
    "more",
    "most",
    "of",
    "policy",
    "principle",
    "than",
    "that",
    "the",
    "to",
}


def _anchor_content_matches(left: str, right: str) -> bool:
    left_tokens = _anchor_tokens(left)
    right_tokens = _anchor_tokens(right)
    if not left_tokens or not right_tokens:
        return left.strip().casefold() == right.strip().casefold()
    overlap = left_tokens & right_tokens
    smaller = min(len(left_tokens), len(right_tokens))
    return len(overlap) >= 2 and (len(overlap) / smaller) >= 0.6


def _anchor_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w']+", text.casefold())
        if token not in _ANCHOR_STOPWORDS
    }


def _dedupe_preserve_order(items: list[T]) -> list[T]:
    seen: set[T] = set()
    result: list[T] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
