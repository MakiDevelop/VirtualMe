from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from virtualme.config import Settings
from virtualme.forget.core import forget_identity
from virtualme.forget.scan import identity_sha256, validate_interviewee_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provably delete one VirtualMe identity.")
    parser.add_argument("interviewee_id")
    parser.add_argument("--dry-run", action="store_true", help="Scan only; do not delete or write a receipt.")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive sha8 confirmation.")
    parser.add_argument("--receipt-dir", type=Path, default=None)
    parser.add_argument(
        "--keep-crisis-stub",
        action="store_true",
        help="Retain metadata-only crisis rows; the proof exits non-zero while identity metadata remains.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_interviewee_id(args.interviewee_id)
    except ValueError as exc:
        parser.error(str(exc))

    digest = identity_sha256(args.interviewee_id)
    if not args.dry_run and not args.yes and not _confirmed(digest[:8]):
        print(f"confirmation_failed sha8={digest[:8]}")
        return 2

    result = asyncio.run(
        forget_identity(
            Settings(),
            args.interviewee_id,
            dry_run=args.dry_run,
            keep_crisis_stub=args.keep_crisis_stub,
            receipt_dir=args.receipt_dir,
        )
    )
    if result.dry_run:
        print(
            json.dumps(
                {
                    "interviewee_sha256": digest,
                    "before": result.before.as_dict(),
                    "errors": list(result.before.errors),
                },
                sort_keys=True,
            )
        )
    else:
        receipt_name = result.receipt_path.name if result.receipt_path else "unwritten"
        print(f"forget sha8={digest[:8]} exit={result.exit_code} receipt={receipt_name}")
    return result.exit_code


def _confirmed(sha8: str) -> bool:
    entered = input(f"Type {sha8} to confirm irreversible deletion: ").strip()
    return entered == sha8


if __name__ == "__main__":
    raise SystemExit(main())
