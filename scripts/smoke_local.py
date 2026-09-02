#!/usr/bin/env python3
# ruff: noqa: RUF001
"""Run the D8 local acceptance flow without LINE or a network LLM call."""

from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.interview import byok
from virtualme.interview.bot import CrisisReply, process_turn
from virtualme.interview.crisis import CRISIS_REPLY, CRISIS_RESUMED_REPLY
from virtualme.interview.question_selector import QuestionSelector
from virtualme.operator.cli import main as operator_main
from virtualme.storage.db import DB, Dimension, Question

INTERVIEWEE_ID = "smoke-local-user"


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if kwargs["max_tokens"] == 120:
            text = json.dumps(
                {
                    "kind": "SUFFICIENT",
                    "depth": "principle",
                    "needs_follow_up": False,
                    "confidence": 0.9,
                }
            )
        elif kwargs["max_tokens"] in (500, 900):
            text = "[]"
        else:
            text = "謝謝你的分享。下一題：你最近做決定時最在意什麼？"
        return type("Response", (), {"content": [_Content(text)]})


class _Client:
    def __init__(self) -> None:
        self.messages = _Messages()


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="virtualme-smoke-") as temp_dir:
            root = Path(temp_dir)
            _configure_environment(root)
            client = _Client()
            asyncio.run(_exercise_interview(root, client))

            locked = _operator_json(["status", INTERVIEWEE_ID, "--json"])
            _require(locked["crisis_locked"] is True, "crisis lock missing from status")

            asyncio.run(_resume_interview(root, client))
            unlocked = _operator_json(["status", INTERVIEWEE_ID, "--json"])
            _require(unlocked["crisis_locked"] is False, "crisis lock did not clear")

            exported = _operator_json(["export", INTERVIEWEE_ID, "--json"])
            _require(Path(exported["zip_path"]).is_file(), "operator export zip missing")
            _require(exported["file_count"] > 0, "operator export contained no files")

            dry_run = _operator_json(
                ["forget", INTERVIEWEE_ID, "--dry-run", "--json"]
            )
            _require(dry_run["dry_run"] is True, "forget did not run in dry-run mode")
            _require(dry_run["counts"]["database"] > 0, "forget dry-run found no DB rows")
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}")
        return 1

    print("PASS local consent/interview/crisis/resume/export/forget-dry-run")
    return 0


async def _exercise_interview(root: Path, client: _Client) -> None:
    db = DB(str(root / "virtualme.db"))
    await db.init()
    selector = _selector()
    settings = _settings(root)

    consent = await process_turn(
        INTERVIEWEE_ID,
        "開始",
        client,
        db,
        selector,
        settings,
    )
    _require(byok.CONSENT_TEXT in consent, "consent prompt missing")

    accepted = await process_turn(
        INTERVIEWEE_ID,
        byok.CONSENT_TEXT,
        client,
        db,
        selector,
        settings,
    )
    _require(accepted == byok.CONSENT_ACCEPTED_REPLY_OPERATOR, "consent was not accepted")

    answer = await process_turn(
        INTERVIEWEE_ID,
        "我最近會先確認證據，再決定要不要改方向。",
        client,
        db,
        selector,
        settings,
    )
    _require(bool(answer), "interview answer produced no question")
    _require(client.messages.calls > 0, "normal interview did not exercise the LLM boundary")

    crisis = await process_turn(
        INTERVIEWEE_ID,
        "我最近一直想死",
        client,
        db,
        selector,
        settings,
    )
    _require(isinstance(crisis, CrisisReply), "crisis did not return CrisisReply")
    _require(crisis == CRISIS_REPLY, "crisis reply changed")


async def _resume_interview(root: Path, client: _Client) -> None:
    resumed = await process_turn(
        INTERVIEWEE_ID,
        "繼續訪談",
        client,
        DB(str(root / "virtualme.db")),
        _selector(),
        _settings(root),
    )
    _require(resumed == CRISIS_RESUMED_REPLY, "resume phrase did not unlock")


def _configure_environment(root: Path) -> None:
    os.environ["ANTHROPIC_API_KEY"] = "smoke-test-key"
    os.environ["DATABASE_URL"] = f"sqlite:///{root / 'virtualme.db'}"
    os.environ["VIRTUALME_BYOK_KEYS_DIR"] = str(root / "keys")
    os.environ["VIRTUALME_PERSONA_EXPORT_DIR"] = str(root / "personas")
    os.environ["VIRTUALME_SNAPSHOT_EXPORT_DIR"] = str(root / "snapshots")


def _settings(root: Path) -> Settings:
    return Settings(
        anthropic_api_key=SecretStr("smoke-test-key"),
        consent_required=True,
        byok_enabled=False,
        byok_keys_dir=str(root / "keys"),
        persona_export_dir=str(root / "personas"),
        snapshot_export_dir=str(root / "snapshots"),
        use_ppa=False,
    )


def _selector() -> QuestionSelector:
    return QuestionSelector(
        {
            1: [
                Question(
                    id="SMOKE-Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="你最近的工作或生活過得怎麼樣？",
                )
            ]
        }
    )


def _operator_json(argv: list[str]) -> dict:
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = operator_main(argv)
    _require(exit_code == 0, f"operator command failed: {argv[0]}")
    return json.loads(output.getvalue())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


if __name__ == "__main__":
    raise SystemExit(main())
