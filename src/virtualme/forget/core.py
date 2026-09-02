from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite

from virtualme.config import sqlite_path
from virtualme.forget.receipt import build_receipt, write_receipt
from virtualme.forget.scan import (
    ScanReport,
    identity_sha256,
    scan_for_identity,
    validate_interviewee_id,
)

if TYPE_CHECKING:
    from virtualme.config import Settings

_GIT_AUTHOR = ["-c", "user.name=VirtualMe", "-c", "user.email=virtualme@localhost"]


@dataclass(frozen=True)
class ForgetResult:
    before: ScanReport
    after: ScanReport | None
    receipt: dict[str, Any] | None
    receipt_path: Path | None
    exit_code: int
    dry_run: bool


async def forget_identity(
    settings: Settings,
    interviewee_id: str,
    *,
    dry_run: bool = False,
    keep_crisis_stub: bool = False,
    receipt_dir: Path | None = None,
) -> ForgetResult:
    """Delete one identity and return the before/after proof material."""
    validate_interviewee_id(interviewee_id)
    requested_at = datetime.now(UTC)
    digest = identity_sha256(interviewee_id)
    before = scan_for_identity(settings, interviewee_id)
    if dry_run:
        return ForgetResult(
            before=before,
            after=None,
            receipt=None,
            receipt_path=None,
            exit_code=0 if not before.errors else 2,
            dry_run=True,
        )

    errors = [f"before_scan:{error}" for error in before.errors]
    git_history_purged: bool | str = False
    database_deleted = False
    try:
        await _delete_database_identity(
            Path(sqlite_path(settings.database_url)),
            interviewee_id,
            keep_crisis_stub=keep_crisis_stub,
        )
        database_deleted = True
    except Exception as exc:
        errors.append(f"database_delete_failed:{type(exc).__name__}")

    if database_deleted:
        git_history_purged, git_errors = _purge_git_history(
            Path(settings.persona_export_dir),
            interviewee_id,
            digest,
        )
        errors.extend(git_errors)
        errors.extend(_delete_managed_files(settings, interviewee_id, digest))

    after = scan_for_identity(settings, interviewee_id)
    errors.extend(f"after_scan:{error}" for error in after.errors)
    completed_at = datetime.now(UTC)
    receipt = build_receipt(
        interviewee_sha256=digest,
        requested_at=requested_at.isoformat(timespec="seconds"),
        completed_at=completed_at.isoformat(timespec="seconds"),
        before=before.as_dict(),
        after=after.as_dict(),
        git_history_purged=git_history_purged,
        errors=errors,
    )
    target_receipt_dir = receipt_dir or Path(settings.persona_export_dir) / "_receipts"
    try:
        receipt_path = write_receipt(target_receipt_dir, receipt, completed_at=completed_at)
    except OSError as exc:
        errors.append(f"receipt_write_failed:{type(exc).__name__}")
        receipt = build_receipt(
            interviewee_sha256=digest,
            requested_at=requested_at.isoformat(timespec="seconds"),
            completed_at=completed_at.isoformat(timespec="seconds"),
            before=before.as_dict(),
            after=after.as_dict(),
            git_history_purged=git_history_purged,
            errors=errors,
        )
        receipt_path = None

    exit_code = 0 if after.total == 0 and not errors and receipt_path is not None else 2
    return ForgetResult(
        before=before,
        after=after,
        receipt=receipt,
        receipt_path=receipt_path,
        exit_code=exit_code,
        dry_run=False,
    )


async def _delete_database_identity(
    database_path: Path,
    interviewee_id: str,
    *,
    keep_crisis_stub: bool,
) -> None:
    if not database_path.is_file():
        raise FileNotFoundError("VirtualMe database does not exist")

    async with aiosqlite.connect(database_path) as conn:
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await _execute_delete(
                conn,
                "redactions",
                """
                DELETE FROM redactions
                WHERE turn_id IN (
                    SELECT turns.id
                    FROM turns
                    JOIN sessions ON sessions.id = turns.session_id
                    WHERE sessions.interviewee_id = ?
                )
                """,
                (interviewee_id,),
            )
            await _execute_delete(
                conn,
                "turns",
                """
                DELETE FROM turns
                WHERE session_id IN (
                    SELECT id FROM sessions WHERE interviewee_id = ?
                )
                """,
                (interviewee_id,),
            )
            await _execute_delete(
                conn,
                "sessions",
                "DELETE FROM sessions WHERE interviewee_id = ?",
                (interviewee_id,),
            )
            for table in (
                "anchors",
                "persona_triples",
                "question_state",
                "blind_tests",
                "subjects",
                "checklist_items",
                "transport_events",
                "persona_download_tokens",
                "persona_download_logs",
            ):
                await _execute_delete(
                    conn,
                    table,
                    f"DELETE FROM {table} WHERE interviewee_id = ?",
                    (interviewee_id,),
                )
            if not keep_crisis_stub:
                await _execute_delete(
                    conn,
                    "crisis_events",
                    "DELETE FROM crisis_events WHERE interviewee_id = ?",
                    (interviewee_id,),
                )
        except Exception:
            await conn.rollback()
            raise
        await conn.commit()


async def _execute_delete(
    conn: aiosqlite.Connection,
    table: str,
    sql: str,
    parameters: tuple[str, ...],
) -> None:
    if "WHERE" not in sql.upper():
        raise ValueError(f"Refusing unscoped delete for {table}")
    await conn.execute(sql, parameters)


def _delete_managed_files(settings: Settings, interviewee_id: str, digest: str) -> list[str]:
    targets = (
        ("byok_key", Path(settings.byok_keys_dir), f"{digest}.key"),
        ("byok_consent", Path(settings.byok_keys_dir), f"{digest}.consent"),
        ("persona_export", Path(settings.persona_export_dir), interviewee_id),
        (
            "persona_package",
            Path(settings.persona_export_dir) / "_packages",
            interviewee_id,
        ),
        (
            "operator_persona_package",
            Path(settings.persona_export_dir) / "_packages",
            digest[:8],
        ),
        ("snapshot_id", Path(settings.snapshot_export_dir), interviewee_id),
        ("snapshot_sha256", Path(settings.snapshot_export_dir), digest),
    )
    errors: list[str] = []
    for surface, root, child in targets:
        try:
            target = _safe_child(root, child)
            if target.is_symlink():
                raise ValueError("symlink target is not deletable")
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        except (OSError, ValueError) as exc:
            errors.append(f"file_delete_failed:{surface}:{type(exc).__name__}")
    return errors


def _safe_child(root: Path, child: str) -> Path:
    root_resolved = root.resolve()
    candidate = root / child
    candidate_resolved = candidate.resolve()
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("Managed path is outside its root") from exc
    return candidate


def _purge_git_history(
    repo: Path,
    interviewee_id: str,
    digest: str,
) -> tuple[bool | str, list[str]]:
    if not (repo / ".git").is_dir():
        return "not_a_repo", []

    errors: list[str] = []
    code, tracked = _run_git(repo, "ls-files", "--", interviewee_id)
    if code != 0:
        errors.append(_git_failure("git_ls_files", code, tracked, interviewee_id, digest))
    elif tracked.strip():
        code, output = _run_git(repo, "rm", "-r", "--cached", "--", interviewee_id)
        if code != 0:
            errors.append(_git_failure("git_rm_cached", code, output, interviewee_id, digest))
        else:
            code, output = _run_git(
                repo,
                *_GIT_AUTHOR,
                "commit",
                "-m",
                f"forget {digest[:8]}",
            )
            if code != 0:
                errors.append(_git_failure("git_commit", code, output, interviewee_id, digest))

    quoted_id = shlex.quote(interviewee_id)
    index_filter = f"git rm -r --cached --ignore-unmatch -- {quoted_id}"
    code, output = _run_git(
        repo,
        "filter-branch",
        "--force",
        "--index-filter",
        index_filter,
        "--",
        "--all",
        env={"FILTER_BRANCH_SQUELCH_WARNING": "1"},
        timeout=300,
    )
    if code != 0:
        errors.append(_git_failure("git_filter_branch", code, output, interviewee_id, digest))
        return False, errors

    code, output = _run_git(repo, "for-each-ref", "--format=%(refname)", "refs/original/")
    if code != 0:
        errors.append(_git_failure("git_list_backup_refs", code, output, interviewee_id, digest))
    else:
        for backup_ref in output.splitlines():
            code, ref_output = _run_git(repo, "update-ref", "-d", backup_ref)
            if code != 0:
                errors.append(
                    _git_failure("git_delete_backup_ref", code, ref_output, interviewee_id, digest)
                )

    for stage, args in (
        ("git_reflog_expire", ("reflog", "expire", "--expire=now", "--all")),
        ("git_gc", ("gc", "--prune=now", "--aggressive")),
    ):
        code, output = _run_git(repo, *args, timeout=300)
        if code != 0:
            errors.append(_git_failure(stage, code, output, interviewee_id, digest))
    return not errors, errors


def _run_git(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> tuple[int, str]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            env=command_env,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, type(exc).__name__
    output = completed.stdout + completed.stderr
    return completed.returncode, output.decode("utf-8", errors="replace").strip()


def _git_failure(
    stage: str,
    code: int,
    output: str,
    interviewee_id: str,
    digest: str,
) -> str:
    sanitized = output.replace(interviewee_id, digest[:8]).replace("\n", " ").strip()
    if len(sanitized) > 500:
        sanitized = sanitized[-500:]
    reason = sanitized or "no_output"
    return f"{stage}_failed:exit_{code}:{reason}"
