from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
import pytest

import virtualme.forget.core as forget_core
from virtualme.config import Settings
from virtualme.forget.__main__ import _confirmed
from virtualme.forget.core import forget_identity
from virtualme.forget.receipt import canonical_receipt_sha256
from virtualme.forget.scan import identity_sha256, scan_for_identity
from virtualme.storage.db import DB

INTERVIEWEE_A = "U-forget-alpha-0001"
INTERVIEWEE_B = "U-forget-beta-0002"

APP_TABLES = {
    "anchors",
    "blind_tests",
    "checklist_items",
    "crisis_events",
    "persona_download_logs",
    "persona_download_tokens",
    "persona_triples",
    "question_state",
    "redactions",
    "sessions",
    "subjects",
    "transport_events",
    "turns",
}


@dataclass(frozen=True)
class SeededSurfaces:
    settings: Settings
    database_path: Path
    export_dir: Path
    receipt_dir: Path


@pytest.fixture
async def seeded(tmp_path: Path) -> SeededSurfaces:
    return await _seed_surfaces(tmp_path, initialize_git=True)


async def test_forget_removes_a_preserves_b_and_writes_verifiable_receipt(
    seeded: SeededSurfaces,
) -> None:
    before_b = scan_for_identity(seeded.settings, INTERVIEWEE_B)
    assert before_b.total > 0
    assert all(value > 0 for value in before_b.counts.values())

    result = await forget_identity(
        seeded.settings,
        INTERVIEWEE_A,
        receipt_dir=seeded.receipt_dir,
    )

    assert result.exit_code == 0, result.receipt
    assert result.after is not None
    assert result.after.total == 0
    assert result.receipt_path is not None and result.receipt_path.is_file()
    assert scan_for_identity(seeded.settings, INTERVIEWEE_A).total == 0
    assert scan_for_identity(seeded.settings, INTERVIEWEE_B).counts == before_b.counts

    remaining = await _identity_row_counts(seeded.database_path, INTERVIEWEE_A)
    preserved = await _identity_row_counts(seeded.database_path, INTERVIEWEE_B)
    assert set(remaining) == APP_TABLES
    assert all(count == 0 for count in remaining.values())
    assert all(count == 1 for count in preserved.values())

    receipt_text = result.receipt_path.read_text(encoding="utf-8")
    assert INTERVIEWEE_A not in receipt_text
    receipt = json.loads(receipt_text)
    assert receipt["interviewee_sha256"] == identity_sha256(INTERVIEWEE_A)
    assert receipt["git_history_purged"] is True
    stored_hash = receipt.pop("receipt_sha256")
    assert stored_hash == canonical_receipt_sha256(receipt)


async def test_dry_run_changes_nothing_and_writes_no_receipt(
    seeded: SeededSurfaces,
) -> None:
    before_scan = scan_for_identity(seeded.settings, INTERVIEWEE_A)
    before_rows = await _identity_row_counts(seeded.database_path, INTERVIEWEE_A)

    result = await forget_identity(
        seeded.settings,
        INTERVIEWEE_A,
        dry_run=True,
        receipt_dir=seeded.receipt_dir,
    )

    assert result.exit_code == 0
    assert result.dry_run is True
    assert result.receipt is None
    assert result.receipt_path is None
    assert scan_for_identity(seeded.settings, INTERVIEWEE_A).counts == before_scan.counts
    assert await _identity_row_counts(seeded.database_path, INTERVIEWEE_A) == before_rows
    assert not seeded.receipt_dir.exists()


async def test_database_failure_rolls_back_every_delete(
    seeded: SeededSurfaces,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_scan = scan_for_identity(seeded.settings, INTERVIEWEE_A)
    before_rows = await _identity_row_counts(seeded.database_path, INTERVIEWEE_A)
    original_execute_delete = forget_core._execute_delete

    async def fail_on_anchors(
        conn: aiosqlite.Connection,
        table: str,
        sql: str,
        parameters: tuple[str, ...],
    ) -> None:
        if table == "anchors":
            raise aiosqlite.OperationalError("simulated")
        await original_execute_delete(conn, table, sql, parameters)

    monkeypatch.setattr(forget_core, "_execute_delete", fail_on_anchors)
    result = await forget_identity(
        seeded.settings,
        INTERVIEWEE_A,
        receipt_dir=seeded.receipt_dir,
    )

    assert result.exit_code == 2
    assert result.receipt is not None
    assert result.receipt["errors"] == ["database_delete_failed:OperationalError"]
    assert await _identity_row_counts(seeded.database_path, INTERVIEWEE_A) == before_rows
    assert scan_for_identity(seeded.settings, INTERVIEWEE_A).counts == before_scan.counts


async def test_path_traversal_identity_is_rejected_before_work(seeded: SeededSurfaces) -> None:
    before_b = scan_for_identity(seeded.settings, INTERVIEWEE_B)
    with pytest.raises(ValueError, match="Invalid interviewee_id"):
        await forget_identity(seeded.settings, "../escape", receipt_dir=seeded.receipt_dir)
    assert scan_for_identity(seeded.settings, INTERVIEWEE_B).counts == before_b.counts
    assert not seeded.receipt_dir.exists()


async def test_non_git_export_is_reported_as_not_a_repo(tmp_path: Path) -> None:
    seeded = await _seed_surfaces(tmp_path, initialize_git=False)

    result = await forget_identity(
        seeded.settings,
        INTERVIEWEE_A,
        receipt_dir=seeded.receipt_dir,
    )

    assert result.exit_code == 0
    assert result.receipt is not None
    assert result.receipt["git_history_purged"] == "not_a_repo"
    assert result.receipt["errors"] == []


async def test_filter_failure_is_sanitized_and_returns_nonzero(
    seeded: SeededSurfaces,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_run_git = forget_core._run_git

    def fail_filter(repo: Path, *args: str, **kwargs: object) -> tuple[int, str]:
        if args and args[0] == "filter-branch":
            return 1, f"could not rewrite {INTERVIEWEE_A}"
        return original_run_git(repo, *args, **kwargs)

    monkeypatch.setattr(forget_core, "_run_git", fail_filter)
    result = await forget_identity(
        seeded.settings,
        INTERVIEWEE_A,
        receipt_dir=seeded.receipt_dir,
    )

    assert result.exit_code == 2
    assert result.receipt is not None
    assert result.receipt["git_history_purged"] is False
    assert any("git_filter_branch_failed" in error for error in result.receipt["errors"])
    assert INTERVIEWEE_A not in json.dumps(result.receipt)


def test_interactive_confirmation_requires_exact_sha8(monkeypatch: pytest.MonkeyPatch) -> None:
    sha8 = identity_sha256(INTERVIEWEE_A)[:8]
    monkeypatch.setattr("builtins.input", lambda _prompt: sha8)
    assert _confirmed(sha8) is True
    monkeypatch.setattr("builtins.input", lambda _prompt: "wrong")
    assert _confirmed(sha8) is False


async def _seed_surfaces(tmp_path: Path, *, initialize_git: bool) -> SeededSurfaces:
    database_path = tmp_path / "virtualme.db"
    keys_dir = tmp_path / "keys"
    export_dir = tmp_path / "personas"
    snapshot_dir = tmp_path / "snapshots"
    receipt_dir = tmp_path / "receipts"
    settings = Settings(
        anthropic_api_key="test",
        database_url=f"sqlite:///{database_path}",
        byok_keys_dir=str(keys_dir),
        persona_export_dir=str(export_dir),
        snapshot_export_dir=str(snapshot_dir),
    )
    await DB(str(database_path)).init()
    await _seed_database(database_path)
    _seed_files(keys_dir, export_dir, snapshot_dir)
    if initialize_git:
        _init_nested_git(export_dir)
    return SeededSurfaces(settings, database_path, export_dir, receipt_dir)


async def _seed_database(database_path: Path) -> None:
    async with aiosqlite.connect(database_path) as conn:
        for offset, interviewee_id in enumerate((INTERVIEWEE_A, INTERVIEWEE_B), start=1):
            session_id = 100 + offset
            turn_id = 200 + offset
            await conn.execute(
                "INSERT INTO sessions(id, interviewee_id, week, notes) VALUES (?, ?, 1, ?)",
                (session_id, interviewee_id, f"notes {interviewee_id}"),
            )
            await conn.execute(
                "INSERT INTO turns(id, session_id, role, content, content_hash) VALUES (?, ?, ?, ?, ?)",
                (
                    turn_id,
                    session_id,
                    "user",
                    f"turn {interviewee_id}",
                    hashlib.sha256(interviewee_id.encode()).hexdigest(),
                ),
            )
            await conn.execute(
                "INSERT INTO redactions(turn_id, category, original, replacement) VALUES (?, ?, ?, ?)",
                (turn_id, "identity", interviewee_id, "[REDACTED]"),
            )
            await conn.execute(
                """
                INSERT INTO anchors(interviewee_id, dimension, layer, content)
                VALUES (?, 'SOUL', 'fact', ?)
                """,
                (interviewee_id, f"anchor {identity_sha256(interviewee_id)}"),
            )
            await conn.execute(
                """
                INSERT INTO persona_triples(
                    interviewee_id, subject, relation, object, source_turn_ids
                ) VALUES (?, ?, 'owns', 'memory', ?)
                """,
                (interviewee_id, interviewee_id, json.dumps([turn_id])),
            )
            await conn.execute(
                """
                INSERT INTO question_state(interviewee_id, question_id, week)
                VALUES (?, ?, 1)
                """,
                (interviewee_id, f"question-{interviewee_id}"),
            )
            await conn.execute(
                """
                INSERT INTO blind_tests(
                    interviewee_id, week, correctness_per_item, overall_accuracy, verdict
                ) VALUES (?, 1, ?, 1.0, 'ship-ready')
                """,
                (interviewee_id, json.dumps({"identity": interviewee_id})),
            )
            await conn.execute(
                "INSERT INTO subjects(interviewee_id, display_name) VALUES (?, ?)",
                (interviewee_id, f"subject {interviewee_id}"),
            )
            await conn.execute(
                """
                INSERT INTO checklist_items(interviewee_id, item_key, label, note)
                VALUES (?, 'seed', 'seed', ?)
                """,
                (interviewee_id, interviewee_id),
            )
            await conn.execute(
                """
                INSERT INTO transport_events(event_id, platform, interviewee_id, message_id)
                VALUES (?, 'line', ?, ?)
                """,
                (f"event-{offset}", interviewee_id, f"message-{interviewee_id}"),
            )
            await conn.execute(
                """
                INSERT INTO persona_download_tokens(
                    token_hash, interviewee_id, zip_path, created_at, expires_at
                ) VALUES (?, ?, ?, '2026-09-01T00:00:00Z', '2026-09-02T00:00:00Z')
                """,
                (f"token-{offset}", interviewee_id, f"/tmp/{interviewee_id}.zip"),
            )
            await conn.execute(
                """
                INSERT INTO persona_download_logs(
                    interviewee_id, token_hash, requested_at, success, zip_path
                ) VALUES (?, ?, '2026-09-01T00:00:00Z', 1, ?)
                """,
                (interviewee_id, f"token-{offset}", f"/tmp/{interviewee_id}.zip"),
            )
            await conn.execute(
                "INSERT INTO crisis_events(interviewee_id, category) VALUES (?, 'self_harm')",
                (interviewee_id,),
            )
        await conn.commit()


def _seed_files(keys_dir: Path, export_dir: Path, snapshot_dir: Path) -> None:
    keys_dir.mkdir(parents=True)
    for interviewee_id in (INTERVIEWEE_A, INTERVIEWEE_B):
        digest = identity_sha256(interviewee_id)
        (keys_dir / f"{digest}.key").write_text("sk-ant-test", encoding="utf-8")
        (keys_dir / f"{digest}.consent").write_text('{"version":"test"}', encoding="utf-8")

        persona_dir = export_dir / interviewee_id
        persona_dir.mkdir(parents=True)
        (persona_dir / "SOUL.md").write_text(f"persona {interviewee_id}", encoding="utf-8")
        package_dir = export_dir / "_packages" / interviewee_id
        package_dir.mkdir(parents=True)
        (package_dir / "persona.zip").write_bytes(interviewee_id.encode())

        snapshot_target = snapshot_dir / interviewee_id
        snapshot_target.mkdir(parents=True)
        (snapshot_target / "snapshot.md").write_text(interviewee_id, encoding="utf-8")
        (snapshot_dir / digest).write_text(digest, encoding="utf-8")


def _init_nested_git(export_dir: Path) -> None:
    _git(export_dir, "init")
    _git(export_dir, "add", "--", INTERVIEWEE_A, INTERVIEWEE_B)
    _git(
        export_dir,
        "-c",
        "user.name=VirtualMe Test",
        "-c",
        "user.email=test@localhost",
        "commit",
        "-m",
        "seed personas",
    )


def _git(repo: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0, (completed.stdout + completed.stderr).decode()


async def _identity_row_counts(database_path: Path, interviewee_id: str) -> dict[str, int]:
    direct_tables = APP_TABLES - {"turns", "redactions"}
    counts: dict[str, int] = {}
    async with aiosqlite.connect(database_path) as conn:
        for table in sorted(direct_tables):
            row = await (
                await conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE interviewee_id = ?",
                    (interviewee_id,),
                )
            ).fetchone()
            counts[table] = int(row[0])
        row = await (
            await conn.execute(
                """
                SELECT COUNT(*)
                FROM turns
                JOIN sessions ON sessions.id = turns.session_id
                WHERE sessions.interviewee_id = ?
                """,
                (interviewee_id,),
            )
        ).fetchone()
        counts["turns"] = int(row[0])
        row = await (
            await conn.execute(
                """
                SELECT COUNT(*)
                FROM redactions
                JOIN turns ON turns.id = redactions.turn_id
                JOIN sessions ON sessions.id = turns.session_id
                WHERE sessions.interviewee_id = ?
                """,
                (interviewee_id,),
            )
        ).fetchone()
        counts["redactions"] = int(row[0])
    return counts
