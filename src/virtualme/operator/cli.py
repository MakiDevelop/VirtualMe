from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import sys
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

from virtualme import byok_admin
from virtualme.config import Settings, sqlite_path
from virtualme.export.persona_package import build_persona_export_package
from virtualme.forget.__main__ import _confirmed as forget_confirmed
from virtualme.forget.__main__ import main as forget_main
from virtualme.interview.turn_state import compute_coverage_snapshot
from virtualme.storage.db import DB, SubjectStatus


@dataclass(frozen=True)
class OperatorSubjectStats:
    interviewee_id: str
    weeks: int = 0
    sessions: int = 0
    last_activity: str | None = None
    status: str | None = None
    crisis_locked: bool = False
    turns: int = 0
    anchors: int = 0
    exports: int = 0

    @property
    def paused(self) -> bool:
        return self.status == SubjectStatus.PAUSED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate a self-hosted VirtualMe instance.")
    _add_output_flags(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List interviewee metadata only.")
    _add_output_flags(list_parser, suppress_default=True)

    for command, help_text in (
        ("status", "Show metadata counts for one interviewee."),
        ("pause", "Pause one interview without storing a turn."),
        ("resume", "Restore the status held before an operator pause."),
        ("export", "Build a persona zip for one interviewee."),
        ("revoke", "Revoke one interviewee's stored BYOK key."),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("interviewee_id")
        _add_output_flags(command_parser, suppress_default=True)

    forget_parser = subparsers.add_parser(
        "forget",
        help="Delegate identity deletion to virtualme.forget.",
    )
    forget_parser.add_argument("interviewee_id")
    forget_parser.add_argument("--dry-run", action="store_true")
    forget_parser.add_argument("--yes", action="store_true")
    _add_output_flags(forget_parser, suppress_default=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "forget":
            return _run_forget(args)
        return asyncio.run(_run(args))
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": type(exc).__name__}, sort_keys=True))
        else:
            print(f"error  {type(exc).__name__}", file=sys.stderr)
        return 1


async def _run(args: argparse.Namespace) -> int:
    settings = Settings()
    db = DB(sqlite_path(settings.database_url))

    if args.command == "list":
        stats = await _load_subject_stats(db)
        payloads = [
            _stats_payload(item, settings, args.show_id, detailed=False) for item in stats
        ]
        _emit_subjects(payloads, as_json=args.json)
        return 0

    interviewee_id = args.interviewee_id
    if args.command == "status":
        rows = await _load_subject_stats(db, interviewee_id)
        stats = rows[0] if rows else OperatorSubjectStats(interviewee_id)
        payload = _stats_payload(stats, settings, args.show_id, detailed=True)
        _emit_record(payload, as_json=args.json)
        return 0

    if args.command == "pause":
        status = await db.set_subject_status(interviewee_id, SubjectStatus.PAUSED.value)
        _emit_action(
            _identity_payload(interviewee_id, args.show_id),
            {"status": status, "paused": True},
            as_json=args.json,
        )
        return 0

    if args.command == "resume":
        status = await db.resume_subject_status(interviewee_id)
        _emit_action(
            _identity_payload(interviewee_id, args.show_id),
            {"status": status, "paused": False},
            as_json=args.json,
        )
        return 0

    if args.command == "export":
        anchors = await db.load_anchors_summary(interviewee_id)
        package = await build_persona_export_package(
            db,
            interviewee_id,
            settings.persona_export_dir,
            compute_coverage_snapshot(anchors),
            package_subdir=_identity_label(interviewee_id, args.show_id),
        )
        _emit_record(
            {
                "zip_path": str(package.zip_path.resolve()),
                "file_count": len(package.written_files),
            },
            as_json=args.json,
        )
        return 0

    if args.command == "revoke":
        byok_args = argparse.Namespace(
            command="revoke",
            keys_dir=settings.byok_keys_dir,
            interviewee=interviewee_id,
        )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code = await byok_admin._run(byok_args)
        _emit_action(
            _identity_payload(interviewee_id, args.show_id),
            {"revoked": exit_code == 0},
            as_json=args.json,
        )
        return exit_code

    raise AssertionError(f"unhandled command: {args.command}")


async def _load_subject_stats(
    db: DB,
    interviewee_id: str | None = None,
) -> list[OperatorSubjectStats]:
    """Load aggregate metadata without selecting transcript or anchor content."""
    await db.init()
    query = """
        WITH identities(interviewee_id) AS (
            SELECT interviewee_id FROM subjects
            UNION SELECT interviewee_id FROM sessions
            UNION SELECT interviewee_id FROM crisis_events
            UNION SELECT interviewee_id FROM anchors
            UNION SELECT interviewee_id FROM persona_triples
            UNION SELECT interviewee_id FROM question_state
            UNION SELECT interviewee_id FROM blind_tests
            UNION SELECT interviewee_id FROM checklist_items
            UNION SELECT interviewee_id FROM transport_events
                WHERE interviewee_id IS NOT NULL
            UNION SELECT interviewee_id FROM persona_download_tokens
            UNION SELECT interviewee_id FROM persona_download_logs
                WHERE interviewee_id IS NOT NULL
        )
        SELECT
            identities.interviewee_id,
            (
                SELECT COUNT(DISTINCT week) FROM sessions
                WHERE sessions.interviewee_id = identities.interviewee_id AND week > 0
            ) AS weeks,
            (
                SELECT COUNT(*) FROM sessions
                WHERE sessions.interviewee_id = identities.interviewee_id
            ) AS sessions,
            (
                SELECT MAX(datetime(activity_at))
                FROM (
                    SELECT COALESCE(updated_at, created_at) AS activity_at
                    FROM subjects WHERE interviewee_id = identities.interviewee_id
                    UNION ALL
                    SELECT COALESCE(ended_at, started_at)
                    FROM sessions WHERE interviewee_id = identities.interviewee_id
                    UNION ALL
                    SELECT turns.ts FROM turns
                    JOIN sessions AS turn_sessions ON turn_sessions.id = turns.session_id
                    WHERE turn_sessions.interviewee_id = identities.interviewee_id
                    UNION ALL
                    SELECT created_at FROM anchors
                    WHERE interviewee_id = identities.interviewee_id
                    UNION ALL
                    SELECT created_at FROM persona_triples
                    WHERE interviewee_id = identities.interviewee_id
                    UNION ALL
                    SELECT COALESCE(resolved_at, ts) FROM crisis_events
                    WHERE interviewee_id = identities.interviewee_id
                    UNION ALL
                    SELECT updated_at FROM transport_events
                    WHERE interviewee_id = identities.interviewee_id
                    UNION ALL
                    SELECT COALESCE(last_downloaded_at, created_at)
                    FROM persona_download_tokens
                    WHERE interviewee_id = identities.interviewee_id
                    UNION ALL
                    SELECT requested_at FROM persona_download_logs
                    WHERE interviewee_id = identities.interviewee_id
                )
            ) AS last_activity,
            (
                SELECT status FROM subjects
                WHERE subjects.interviewee_id = identities.interviewee_id
            ) AS status,
            EXISTS(
                SELECT 1 FROM crisis_events
                WHERE crisis_events.interviewee_id = identities.interviewee_id
                    AND resolved_at IS NULL
            ) AS crisis_locked,
            (
                SELECT COUNT(*) FROM turns
                JOIN sessions AS turn_sessions ON turn_sessions.id = turns.session_id
                WHERE turn_sessions.interviewee_id = identities.interviewee_id
            ) AS turns,
            (
                SELECT COUNT(*) FROM anchors
                WHERE anchors.interviewee_id = identities.interviewee_id
            ) AS anchors,
            COALESCE((
                SELECT export_count FROM subjects
                WHERE subjects.interviewee_id = identities.interviewee_id
            ), 0) AS exports
        FROM identities
        WHERE (? IS NULL OR identities.interviewee_id = ?)
        ORDER BY identities.interviewee_id
    """
    async with aiosqlite.connect(db.path) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(query, (interviewee_id, interviewee_id))).fetchall()
    return [
        OperatorSubjectStats(
            interviewee_id=str(row["interviewee_id"]),
            weeks=int(row["weeks"]),
            sessions=int(row["sessions"]),
            last_activity=str(row["last_activity"]) if row["last_activity"] else None,
            status=str(row["status"]) if row["status"] else None,
            crisis_locked=bool(row["crisis_locked"]),
            turns=int(row["turns"]),
            anchors=int(row["anchors"]),
            exports=int(row["exports"]),
        )
        for row in rows
    ]


def _stats_payload(
    stats: OperatorSubjectStats,
    settings: Settings,
    show_id: bool,
    *,
    detailed: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **_identity_payload(stats.interviewee_id, show_id),
        "weeks": stats.weeks,
        "sessions": stats.sessions,
        "last_activity": stats.last_activity or "-",
        "consent_version": _consent_version(settings.byok_keys_dir, stats.interviewee_id),
        "crisis_locked": stats.crisis_locked,
        "paused": stats.paused,
    }
    if detailed:
        payload.update(
            {
                "turns": stats.turns,
                "anchors": stats.anchors,
                "exports": stats.exports,
            }
        )
    return payload


def _consent_version(keys_dir: str, interviewee_id: str) -> str:
    digest = hashlib.sha256(interviewee_id.encode("utf-8")).hexdigest()
    path = Path(keys_dir) / f"{digest}.consent"
    if not path.is_file():
        return "-"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        return "invalid"
    version = record.get("version") if isinstance(record, dict) else None
    return str(version) if version else "invalid"


def _run_forget(args: argparse.Namespace) -> int:
    forwarded = [args.interviewee_id]
    if args.dry_run:
        forwarded.append("--dry-run")
        if args.yes:
            forwarded.append("--yes")
    elif args.yes:
        forwarded.append("--yes")
    elif args.json:
        print(
            json.dumps(
                {
                    **_identity_payload(args.interviewee_id, args.show_id),
                    "error": "confirmation_required",
                    "exit_code": 2,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    else:
        sha8 = _identity_label(args.interviewee_id, show_id=False)
        if not forget_confirmed(sha8):
            _emit_action(
                _identity_payload(args.interviewee_id, args.show_id),
                {"forgotten": False, "exit_code": 2},
                as_json=False,
            )
            return 2
        forwarded.append("--yes")

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = forget_main(forwarded)

    identity = _identity_payload(args.interviewee_id, args.show_id)
    if args.dry_run:
        try:
            raw_result = json.loads(stdout.getvalue())
        except json.JSONDecodeError:
            raw_result = {}
        payload = {
            **identity,
            "dry_run": True,
            "counts": raw_result.get("before", {}),
            "errors": raw_result.get("errors", []),
            "exit_code": exit_code,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            rows = [("identity", next(iter(identity.values()))), ("dry_run", True)]
            rows.extend((str(key), value) for key, value in payload["counts"].items())
            rows.append(("exit_code", exit_code))
            _print_table(("field", "value"), rows)
        return exit_code

    _emit_action(
        identity,
        {"forgotten": exit_code == 0, "exit_code": exit_code},
        as_json=args.json,
    )
    return exit_code


def _add_output_flags(
    parser: argparse.ArgumentParser,
    *,
    suppress_default: bool = False,
) -> None:
    default: bool | str = argparse.SUPPRESS if suppress_default else False
    parser.add_argument("--json", action="store_true", default=default)
    parser.add_argument("--show-id", action="store_true", default=default)


def _identity_label(interviewee_id: str, show_id: bool) -> str:
    if show_id:
        return interviewee_id
    return hashlib.sha256(interviewee_id.encode("utf-8")).hexdigest()[:8]


def _identity_payload(interviewee_id: str, show_id: bool) -> dict[str, str]:
    return {"id" if show_id else "sha8": _identity_label(interviewee_id, show_id)}


def _emit_subjects(payloads: list[dict[str, Any]], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"subjects": payloads}, ensure_ascii=False, sort_keys=True))
        return
    identity_header = "id" if payloads and "id" in payloads[0] else "sha8"
    headers = (
        identity_header,
        "weeks",
        "sessions",
        "last_activity",
        "consent_version",
        "crisis_locked",
        "paused",
    )
    _print_table(headers, [tuple(item[header] for header in headers) for item in payloads])


def _emit_record(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    _print_table(("field", "value"), list(payload.items()))


def _emit_action(
    identity: dict[str, str],
    values: dict[str, Any],
    *,
    as_json: bool,
) -> None:
    _emit_record({**identity, **values}, as_json=as_json)


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    rendered_rows = [[_format_cell(cell) for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in rendered_rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row, strict=True)]
    print("  ".join(header.ljust(width) for header, width in zip(headers, widths, strict=True)))
    print("  ".join("-" * width for width in widths))
    for row in rendered_rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)))


def _format_cell(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
