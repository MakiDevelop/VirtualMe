from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import aiosqlite
from pydantic import SecretStr

from virtualme.interview import byok
from virtualme.interview.bot import OPERATOR_PAUSED_REPLY, process_turn
from virtualme.interview.question_selector import QuestionSelector
from virtualme.operator import cli as operator_cli
from virtualme.storage.db import DB, Dimension, Layer, Question, SubjectStatus

INTERVIEWEE_ID = "U-operator-private-identity-0001"
TURN_MARKER = "TURN-CONTENT-MUST-NEVER-LEAK-7f6d"
ANCHOR_MARKER = "ANCHOR-CONTENT-MUST-NEVER-LEAK-a2c9"
REDACTION_MARKER = "REDACTION-ORIGINAL-MUST-NEVER-LEAK-e4b1"


class _ExplodingMessages:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        raise AssertionError("paused interviews must not call the LLM")


class _ExplodingClient:
    def __init__(self) -> None:
        self.messages = _ExplodingMessages()


def _configure(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    db_path = tmp_path / "virtualme.db"
    keys_dir = tmp_path / "keys"
    export_dir = tmp_path / "personas"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-operator-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VIRTUALME_BYOK_KEYS_DIR", str(keys_dir))
    monkeypatch.setenv("VIRTUALME_PERSONA_EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("VIRTUALME_SNAPSHOT_EXPORT_DIR", str(tmp_path / "snapshots"))
    return db_path, keys_dir, export_dir


async def _seed_sensitive_metadata(db_path: Path, keys_dir: Path) -> None:
    db = DB(str(db_path))
    await db.init()
    await db.get_or_create_subject(INTERVIEWEE_ID)
    session = await db.get_or_create_session(INTERVIEWEE_ID, week=1)
    turn = await db.save_turn(session.id, "user", TURN_MARKER)
    await db.save_anchor(
        INTERVIEWEE_ID,
        Dimension.SOUL,
        Layer.FACT,
        ANCHOR_MARKER,
        [turn.id],
        ["Q1"],
    )
    async with aiosqlite.connect(db.path) as conn:
        await conn.execute(
            """
            INSERT INTO redactions(turn_id, category, original, replacement)
            VALUES (?, 'identity', ?, '[REDACTED]')
            """,
            (turn.id, REDACTION_MARKER),
        )
        await conn.commit()
    byok.store_consent(str(keys_dir), INTERVIEWEE_ID)


def test_status_and_list_never_emit_sensitive_content_or_raw_id(
    tmp_path,
    monkeypatch,
    capsys,
):
    db_path, keys_dir, _export_dir = _configure(monkeypatch, tmp_path)
    asyncio.run(_seed_sensitive_metadata(db_path, keys_dir))
    sha8 = hashlib.sha256(INTERVIEWEE_ID.encode()).hexdigest()[:8]

    assert operator_cli.main(["status", INTERVIEWEE_ID]) == 0
    status_output = capsys.readouterr().out
    assert sha8 in status_output
    assert INTERVIEWEE_ID not in status_output
    assert TURN_MARKER not in status_output
    assert ANCHOR_MARKER not in status_output
    assert REDACTION_MARKER not in status_output

    assert operator_cli.main(["list", "--json"]) == 0
    list_output = capsys.readouterr().out
    payload = json.loads(list_output)
    assert payload["subjects"][0]["sha8"] == sha8
    assert INTERVIEWEE_ID not in list_output
    assert TURN_MARKER not in list_output
    assert ANCHOR_MARKER not in list_output
    assert REDACTION_MARKER not in list_output

    assert operator_cli.main(["status", INTERVIEWEE_ID, "--show-id"]) == 0
    assert INTERVIEWEE_ID in capsys.readouterr().out


def test_pause_blocks_before_consent_llm_and_turn_storage_then_resume_restores(
    tmp_path,
    monkeypatch,
    capsys,
):
    db_path, keys_dir, _export_dir = _configure(monkeypatch, tmp_path)
    db = DB(str(db_path))

    async def seed() -> int:
        await db.init()
        await db.get_or_create_subject(INTERVIEWEE_ID)
        await db.set_subject_status(INTERVIEWEE_ID, SubjectStatus.EXTRACTED.value)
        session = await db.get_or_create_session(INTERVIEWEE_ID, week=1)
        await db.save_turn(session.id, "assistant", "existing question")
        return session.id

    session_id = asyncio.run(seed())
    assert operator_cli.main(["pause", INTERVIEWEE_ID]) == 0
    capsys.readouterr()

    client = _ExplodingClient()
    settings = operator_cli.Settings(
        anthropic_api_key=SecretStr("test"),
        consent_required=True,
        byok_enabled=False,
        byok_keys_dir=str(keys_dir),
    )
    selector = QuestionSelector(
        {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="How has work been?",
                )
            ]
        }
    )

    before = asyncio.run(db.count_turns(session_id))
    reply = asyncio.run(
        process_turn(
            INTERVIEWEE_ID,
            "a normal answer",
            client,
            db,
            selector,
            settings,
        )
    )
    assert reply == OPERATOR_PAUSED_REPLY
    assert client.messages.calls == 0
    assert asyncio.run(db.count_turns(session_id)) == before

    assert operator_cli.main(["resume", INTERVIEWEE_ID, "--json"]) == 0
    resume_payload = json.loads(capsys.readouterr().out)
    assert resume_payload["status"] == SubjectStatus.EXTRACTED
    assert asyncio.run(db.get_subject_status(INTERVIEWEE_ID)) == SubjectStatus.EXTRACTED


def test_pause_creates_minimal_subject_when_missing(tmp_path, monkeypatch, capsys):
    db_path, _keys_dir, _export_dir = _configure(monkeypatch, tmp_path)

    assert operator_cli.main(["pause", INTERVIEWEE_ID, "--json"]) == 0
    capsys.readouterr()
    db = DB(str(db_path))
    assert asyncio.run(db.get_subject_status(INTERVIEWEE_ID)) == SubjectStatus.PAUSED

    assert operator_cli.main(["resume", INTERVIEWEE_ID]) == 0
    capsys.readouterr()
    assert asyncio.run(db.get_subject_status(INTERVIEWEE_ID)) == SubjectStatus.EXTRACTING


def test_pause_migrates_legacy_subject_and_restores_original_status(tmp_path):
    db_path = tmp_path / "legacy.db"

    async def exercise() -> tuple[str, set[str]]:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                """
                CREATE TABLE subjects (
                    interviewee_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    domain TEXT NOT NULL DEFAULT 'unspecified',
                    goal TEXT,
                    status TEXT NOT NULL DEFAULT 'extracting',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT
                )
                """
            )
            await conn.execute(
                "INSERT INTO subjects(interviewee_id, status) VALUES (?, 'deployed')",
                (INTERVIEWEE_ID,),
            )
            await conn.commit()

        db = DB(str(db_path))
        await db.set_subject_status(INTERVIEWEE_ID, SubjectStatus.PAUSED.value)
        restored = await db.resume_subject_status(INTERVIEWEE_ID)
        async with aiosqlite.connect(db_path) as conn:
            columns = {
                str(row[1])
                for row in await (await conn.execute("PRAGMA table_info(subjects)")).fetchall()
            }
        return restored, columns

    restored, columns = asyncio.run(exercise())
    assert restored == SubjectStatus.DEPLOYED
    assert {"paused_from_status", "export_count"} <= columns


def test_export_returns_existing_sha8_path_and_increments_count(
    tmp_path,
    monkeypatch,
    capsys,
):
    db_path, _keys_dir, _export_dir = _configure(monkeypatch, tmp_path)

    async def seed() -> None:
        db = DB(str(db_path))
        await db.init()
        await db.save_anchor(
            INTERVIEWEE_ID,
            Dimension.SOUL,
            Layer.FACT,
            "prefers direct evidence",
            [],
            ["Q1"],
        )

    asyncio.run(seed())
    assert operator_cli.main(["export", INTERVIEWEE_ID, "--json"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    zip_path = Path(payload["zip_path"])
    sha8 = hashlib.sha256(INTERVIEWEE_ID.encode()).hexdigest()[:8]

    assert zip_path.is_file()
    assert zip_path.parent.name == sha8
    assert payload["file_count"] > 0
    assert INTERVIEWEE_ID not in output

    assert operator_cli.main(["status", INTERVIEWEE_ID, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["exports"] == 1


def test_revoke_delegates_to_existing_byok_admin_logic(
    tmp_path,
    monkeypatch,
    capsys,
):
    _db_path, keys_dir, _export_dir = _configure(monkeypatch, tmp_path)
    byok.store_key(str(keys_dir), INTERVIEWEE_ID, "sk-ant-test")

    assert operator_cli.main(["revoke", INTERVIEWEE_ID, "--json"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["revoked"] is True
    assert INTERVIEWEE_ID not in output
    assert not byok.has_key(str(keys_dir), INTERVIEWEE_ID)


def test_forget_forwards_to_d7_cli_without_reimplementing(
    tmp_path,
    monkeypatch,
    capsys,
):
    _configure(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    def fake_forget(argv):
        calls.append(list(argv))
        print(json.dumps({"before": {"database": 3}, "errors": []}))
        return 0

    monkeypatch.setattr(operator_cli, "forget_main", fake_forget)
    assert (
        operator_cli.main(
            ["forget", INTERVIEWEE_ID, "--dry-run", "--yes", "--json"]
        )
        == 0
    )

    assert calls == [[INTERVIEWEE_ID, "--dry-run", "--yes"]]
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["counts"] == {"database": 3}
    assert INTERVIEWEE_ID not in output


def test_forget_reuses_d7_confirmation_before_forwarding(
    tmp_path,
    monkeypatch,
    capsys,
):
    _configure(monkeypatch, tmp_path)
    confirmations: list[str] = []
    calls: list[list[str]] = []

    def fake_confirm(sha8: str) -> bool:
        confirmations.append(sha8)
        return True

    def fake_forget(argv):
        calls.append(list(argv))
        print("forget complete")
        return 0

    monkeypatch.setattr(operator_cli, "forget_confirmed", fake_confirm)
    monkeypatch.setattr(operator_cli, "forget_main", fake_forget)

    assert operator_cli.main(["forget", INTERVIEWEE_ID]) == 0
    output = capsys.readouterr().out
    sha8 = hashlib.sha256(INTERVIEWEE_ID.encode()).hexdigest()[:8]
    assert confirmations == [sha8]
    assert calls == [[INTERVIEWEE_ID, "--yes"]]
    assert sha8 in output
    assert INTERVIEWEE_ID not in output
