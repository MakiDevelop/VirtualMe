from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path

import aiosqlite
from pydantic import BaseModel


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


def _schema_path() -> Path:
    return Path(__file__).with_name("schema.sql")


async def init_db(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as conn:
        await conn.executescript(_schema_path().read_text())
        await conn.commit()


class DB:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        await init_db(self.path)

    async def get_or_create_session(self, interviewee_id: str, week: int) -> Session:
        await self.init()
        async with aiosqlite.connect(self.path) as conn:
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

    async def save_turn(self, session_id: int, role: str, content: str) -> Turn:
        digest = hashlib.sha256(f"{session_id}:{role}:{content}".encode()).hexdigest()
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute(
                """
                INSERT OR IGNORE INTO turns(session_id, role, content, content_hash)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, digest),
            )
            await conn.commit()
            row = await (
                await conn.execute("SELECT * FROM turns WHERE content_hash = ?", (digest,))
            ).fetchone()
        return Turn(**dict(row))

    async def save_anchor(
        self,
        interviewee_id: str,
        dimension: Dimension,
        layer: Layer,
        content: str,
        source_turn_ids: list[int],
        source_question_ids: list[str] | None = None,
    ) -> Anchor:
        question_ids = source_question_ids if source_question_ids is not None else []
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                """
                INSERT INTO anchors(interviewee_id, dimension, layer, content, source_turn_ids, source_question_ids)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (interviewee_id, dimension, layer, content, json.dumps(source_turn_ids), json.dumps(question_ids)),
            )
            await conn.commit()
            anchor_id = cur.lastrowid
        return Anchor(
            id=anchor_id,
            interviewee_id=interviewee_id,
            dimension=dimension,
            layer=layer,
            content=content,
            source_turn_ids=source_turn_ids,
        )

    async def mark_triangulated(self, anchor_id: int) -> None:
        async with aiosqlite.connect(self.path) as conn:
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

    async def _fetch_anchors(self, interviewee_id: str, triangulated: bool | None = None):
        clause = "AND triangulated = ?" if triangulated is not None else ""
        params = (
            (interviewee_id, int(triangulated))
            if triangulated is not None
            else (interviewee_id,)
        )
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                f"SELECT * FROM anchors WHERE interviewee_id = ? {clause} ORDER BY created_at",
                params,
            )
            return await cur.fetchall()


def _anchor_from_row(row: aiosqlite.Row) -> Anchor:
    source_question_ids_raw = row["source_question_ids"] if "source_question_ids" in row.keys() else "[]"
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
