from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from virtualme.config import sqlite_path

if TYPE_CHECKING:
    from virtualme.config import Settings

SCAN_SURFACES = (
    "database",
    "byok_keys",
    "persona_exports",
    "snapshot_exports",
    "git_content",
    "git_paths",
)


@dataclass(frozen=True)
class ScanReport:
    counts: dict[str, int]
    errors: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def as_dict(self) -> dict[str, int]:
        return {surface: self.counts[surface] for surface in SCAN_SURFACES}


def identity_sha256(interviewee_id: str) -> str:
    return hashlib.sha256(interviewee_id.encode("utf-8")).hexdigest()


def validate_interviewee_id(interviewee_id: str) -> None:
    if (
        not interviewee_id
        or ".." in interviewee_id
        or "/" in interviewee_id
        or "\\" in interviewee_id
        or any(ord(char) < 32 for char in interviewee_id)
    ):
        raise ValueError("Invalid interviewee_id")


def scan_for_identity(settings: Settings, interviewee_id: str) -> ScanReport:
    """Count identity traces across SQLite, managed files, and nested git history."""
    validate_interviewee_id(interviewee_id)
    digest = identity_sha256(interviewee_id)
    counts = dict.fromkeys(SCAN_SURFACES, 0)
    errors: list[str] = []

    database_count, database_errors = _scan_database(
        Path(sqlite_path(settings.database_url)),
        (interviewee_id, digest),
    )
    counts["database"] = database_count
    errors.extend(database_errors)

    directory_specs = (
        ("byok_keys", Path(settings.byok_keys_dir), ()),
        (
            "persona_exports",
            Path(settings.persona_export_dir),
            (Path(settings.persona_export_dir) / "_receipts",),
        ),
        ("snapshot_exports", Path(settings.snapshot_export_dir), ()),
    )
    for surface, root, excluded in directory_specs:
        count, scan_errors = _scan_directory(root, (interviewee_id, digest), excluded)
        counts[surface] = count
        errors.extend(f"{surface}:{error}" for error in scan_errors)

    git_counts, git_errors = _scan_git_history(
        Path(settings.persona_export_dir),
        interviewee_id,
        digest,
    )
    counts.update(git_counts)
    errors.extend(git_errors)
    return ScanReport(counts=counts, errors=tuple(errors))


def _scan_database(database_path: Path, needles: tuple[str, str]) -> tuple[int, list[str]]:
    if not database_path.is_file():
        return 0, ["database_missing"]

    count = 0
    try:
        with sqlite3.connect(database_path) as conn:
            tables = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
            for (table,) in tables:
                quoted_table = _quote_identifier(str(table))
                columns = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
                for column in columns:
                    column_name = str(column[1])
                    declared_type = str(column[2]).upper()
                    if "TEXT" not in declared_type:
                        continue
                    quoted_column = _quote_identifier(column_name)
                    patterns = tuple(f"%{_escape_like(needle)}%" for needle in needles)
                    row = conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM {quoted_table}
                        WHERE {quoted_column} LIKE ? ESCAPE '\\'
                           OR {quoted_column} LIKE ? ESCAPE '\\'
                        """,
                        patterns,
                    ).fetchone()
                    count += int(row[0]) if row else 0
    except (OSError, sqlite3.Error):
        return count, ["database_scan_failed"]
    return count, []


def _scan_directory(
    root: Path,
    needles: tuple[str, str],
    excluded_roots: tuple[Path, ...],
) -> tuple[int, list[str]]:
    if not root.exists():
        return 0, []

    root_resolved = root.resolve()
    excluded_resolved = tuple(path.resolve() for path in excluded_roots)
    needle_bytes = tuple(needle.encode("utf-8") for needle in needles)
    count = 0
    errors: list[str] = []
    try:
        entries = root.rglob("*")
        for entry in entries:
            try:
                resolved = entry.resolve()
                resolved.relative_to(root_resolved)
            except (OSError, ValueError):
                errors.append("path_outside_root")
                continue
            if any(_is_within(resolved, excluded) for excluded in excluded_resolved):
                continue

            relative_name = entry.relative_to(root).as_posix()
            count += sum(relative_name.count(needle) for needle in needles)
            if not entry.is_file() or entry.is_symlink():
                continue
            try:
                content = entry.read_bytes()
            except OSError:
                errors.append("file_read_failed")
                continue
            count += sum(content.count(needle) for needle in needle_bytes)
    except OSError:
        errors.append("directory_scan_failed")
    return count, errors


def _scan_git_history(
    repo: Path,
    interviewee_id: str,
    digest: str,
) -> tuple[dict[str, int], list[str]]:
    counts = {"git_content": 0, "git_paths": 0}
    if not (repo / ".git").is_dir():
        return counts, []

    code, revision_output = _run_git(repo, "rev-list", "--all")
    if code != 0:
        return counts, [f"git_rev_list_failed:exit_{code}"]
    revisions = [line for line in revision_output.splitlines() if line]
    if not revisions:
        return counts, []

    unique_content_hits: set[str] = set()
    for needle in (interviewee_id, digest):
        code, output = _run_git(
            repo,
            "grep",
            "-I",
            "-F",
            "-n",
            "-e",
            needle,
            *revisions,
        )
        if code not in (0, 1):
            return counts, [f"git_grep_failed:exit_{code}"]
        for line in output.splitlines():
            _revision, separator, hit = line.partition(":")
            unique_content_hits.add(hit if separator else line)
    counts["git_content"] = len(unique_content_hits)

    matching_commits: set[str] = set()
    for path_name in (interviewee_id, digest):
        code, output = _run_git(repo, "log", "--all", "--format=%H", "--", path_name)
        if code != 0:
            return counts, [f"git_log_failed:exit_{code}"]
        matching_commits.update(line for line in output.splitlines() if line)
    counts["git_paths"] = len(matching_commits)
    return counts, []


def _run_git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, type(exc).__name__
    output = completed.stdout + completed.stderr
    return completed.returncode, output.decode("utf-8", errors="replace").strip()


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
