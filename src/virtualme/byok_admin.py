"""Operator CLI for BYOK key management — BW5.

Keys are stored hashed, so the operator can revoke or replace a key but can
never read a stored key back. ``list`` shows hashes and timestamps only.

Usage::

    python -m virtualme.byok_admin list
    python -m virtualme.byok_admin revoke --interviewee <id>
    python -m virtualme.byok_admin replace --interviewee <id>   # key on stdin

``replace`` reads the new key from stdin and validates it before storing, so a
bad paste is rejected instead of silently breaking the next interview turn.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from virtualme.interview import byok

DEFAULT_KEYS_DIR = "./data/keys"


async def _run(args: argparse.Namespace) -> int:
    if args.command == "list":
        return _cmd_list(args.keys_dir)
    if args.command == "revoke":
        removed = byok.delete_key(args.keys_dir, args.interviewee)
        if removed:
            print(f"revoked: key removed for {args.interviewee}")
            return 0
        print(f"no-op: no stored key for {args.interviewee}", file=sys.stderr)
        return 1
    if args.command == "replace":
        return await _cmd_replace(args.keys_dir, args.interviewee)
    raise AssertionError(f"unhandled command: {args.command}")


def _cmd_list(keys_dir: str) -> int:
    directory = Path(keys_dir)
    if not directory.is_dir():
        print(f"no keys directory at {keys_dir}")
        return 0
    key_files = sorted(directory.glob("*.key"))
    if not key_files:
        print(f"no stored keys in {keys_dir}")
        return 0
    print(f"{len(key_files)} stored key(s) in {keys_dir}:")
    for path in key_files:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(timespec="seconds")
        print(f"  {path.stem}  (updated {mtime})")
    return 0


async def _cmd_replace(keys_dir: str, interviewee_id: str) -> int:
    new_key = sys.stdin.read().strip()
    if not new_key.startswith(byok.KEY_PREFIX):
        print(f"rejected: pasted value is not a Claude API key ({byok.KEY_PREFIX}…)",
              file=sys.stderr)
        return 1
    if not await byok.validate_api_key(new_key):
        print("rejected: key failed validation", file=sys.stderr)
        return 1
    byok.store_key(keys_dir, interviewee_id, new_key)
    print(f"replaced: validated key stored for {interviewee_id}")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VirtualMe BYOK key management.")
    parser.add_argument("--keys-dir", default=DEFAULT_KEYS_DIR, help="BYOK key store directory.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List stored key hashes and timestamps.")
    revoke = sub.add_parser("revoke", help="Remove a stored key.")
    revoke.add_argument("--interviewee", required=True)
    replace = sub.add_parser("replace", help="Validate and store a new key (key read from stdin).")
    replace.add_argument("--interviewee", required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
