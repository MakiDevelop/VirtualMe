from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from virtualme import __version__


def canonical_receipt_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_receipt(
    *,
    interviewee_sha256: str,
    requested_at: str,
    completed_at: str,
    before: dict[str, int],
    after: dict[str, int],
    git_history_purged: bool | str,
    errors: list[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "interviewee_sha256": interviewee_sha256,
        "requested_at": requested_at,
        "completed_at": completed_at,
        "version": __version__,
        "before": before,
        "after": after,
        "git_history_purged": git_history_purged,
        "errors": errors,
    }
    return {**payload, "receipt_sha256": canonical_receipt_sha256(payload)}


def write_receipt(
    receipt_dir: Path,
    receipt: dict[str, Any],
    *,
    completed_at: datetime | None = None,
) -> Path:
    timestamp = completed_at or datetime.now(UTC)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    sha8 = str(receipt["interviewee_sha256"])[:8]
    stamp = timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = receipt_dir / f"forget-{sha8}-{stamp}.json"
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
