"""Tests for the BW6 persona auto-export with local-only git versioning."""

from pathlib import Path

from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.export.auto import auto_export_persona
from virtualme.interview.bot import process_turn
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB, Dimension, Layer, Question

CLOSING_MESSAGE = "今天先這樣"


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    async def create(self, **kwargs):
        max_tokens = kwargs["max_tokens"]
        if max_tokens == 10:
            text = "principle"
        elif max_tokens == 500:
            text = "[]"
        elif max_tokens == 900:
            text = (
                '[{"subject": "interviewee", "relation": "preference", '
                '"object": "direct flow", "source_turn_ids": [1], "confidence": 0.9}]'
            )
        else:
            text = "OK"
        return type("Response", (), {"content": [_Content(text)]})


class _Claude:
    def __init__(self):
        self.messages = _Messages()


def _commit_count(repo: Path) -> int:
    log = repo / ".git" / "logs" / "HEAD"
    if not log.is_file():
        return 0
    return len([line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()])


def _has_remote(repo: Path) -> bool:
    config = repo / ".git" / "config"
    return config.is_file() and "[remote " in config.read_text(encoding="utf-8")


async def _new_db(tmp_path) -> DB:
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    return db


# --- auto_export_persona unit tests ------------------------------------------


async def test_auto_export_produces_eight_dimension_files(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor("u1", Dimension.VOICE, Layer.PATTERN, "speaks plainly", [1], ["Q1"])
    export_dir = tmp_path / "personas"

    written = await auto_export_persona(db, "u1", str(export_dir))

    subject_dir = export_dir / "u1"
    for dimension in Dimension:
        assert (subject_dir / f"{dimension.value}.md").is_file()
    assert (subject_dir / "manifest.json").is_file()
    assert (subject_dir / "START_HERE.md").is_file()
    assert len(written) >= 8


async def test_auto_export_creates_local_only_git_repo(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor("u1", Dimension.VOICE, Layer.PATTERN, "x", [1], ["Q1"])
    export_dir = tmp_path / "personas"

    await auto_export_persona(db, "u1", str(export_dir))

    assert (export_dir / ".git").is_dir()
    assert _commit_count(export_dir) >= 1
    assert not _has_remote(export_dir)


async def test_auto_export_versions_each_export_as_a_commit(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor("u1", Dimension.VOICE, Layer.PATTERN, "first", [1], ["Q1"])
    export_dir = tmp_path / "personas"

    await auto_export_persona(db, "u1", str(export_dir))
    assert _commit_count(export_dir) == 1

    await db.save_anchor("u1", Dimension.BOUNDARIES, Layer.PRINCIPLE, "second", [2], ["Q2"])
    await auto_export_persona(db, "u1", str(export_dir))
    assert _commit_count(export_dir) == 2


async def test_auto_export_rejects_path_traversal_interviewee_id(tmp_path):
    db = await _new_db(tmp_path)

    for bad_id in ["../x", "nested/x", "nested\\x", "bad\nid", "bad..id"]:
        try:
            await auto_export_persona(db, bad_id, str(tmp_path / "personas"))
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted unsafe interviewee_id: {bad_id!r}")


async def test_auto_export_skips_commit_when_repo_has_remote(tmp_path, caplog):
    db = await _new_db(tmp_path)
    await db.save_anchor("u1", Dimension.VOICE, Layer.PATTERN, "x", [1], ["Q1"])
    export_dir = tmp_path / "personas"
    export_dir.mkdir()
    await auto_export_persona(db, "u1", str(export_dir))
    code, out = await _run_git_for_test(export_dir, "remote", "add", "origin", "https://example.com/repo.git")
    assert code == 0, out
    await db.save_anchor("u1", Dimension.BOUNDARIES, Layer.PRINCIPLE, "y", [2], ["Q2"])

    with caplog.at_level("ERROR"):
        await auto_export_persona(db, "u1", str(export_dir))

    assert _commit_count(export_dir) == 1
    assert "has remote configured" in caplog.text


async def _run_git_for_test(repo: Path, *args: str) -> tuple[int, str]:
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(repo),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout.decode("utf-8", errors="replace").strip()


# --- process_turn integration ------------------------------------------------


def _settings(tmp_path, *, enabled: bool) -> Settings:
    return Settings(
        anthropic_api_key=SecretStr("operator-key"),
        use_ppa=False,
        persona_auto_export=enabled,
        persona_export_dir=str(tmp_path / "personas"),
    )


async def test_process_turn_exports_on_sufficient_close(tmp_path):
    db = await _new_db(tmp_path)
    # Single-week pool: round 1 reaches the round cap, so extraction is sufficient.
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="How has work been?")]}
    )
    settings = _settings(tmp_path, enabled=True)

    await process_turn("u1", CLOSING_MESSAGE, _Claude(), db, selector, settings)

    export_dir = tmp_path / "personas"
    assert (export_dir / "u1" / "SOUL.md").is_file()
    assert (export_dir / ".git").is_dir()
    assert _commit_count(export_dir) == 1


async def test_process_turn_stages_when_not_sufficient(tmp_path):
    db = await _new_db(tmp_path)
    # Two-week pool: closing at week 1 is below the round cap and VOICE/
    # BOUNDARIES are empty, so extraction is not yet sufficient.
    selector = QuestionSelector(
        {
            1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="How has work been?")],
            2: [Question(id="Q2", week=2, dimension=Dimension.SKILL, text="How do you work?")],
        }
    )
    settings = _settings(tmp_path, enabled=True)

    await process_turn("u1", CLOSING_MESSAGE, _Claude(), db, selector, settings)

    assert not (tmp_path / "personas").exists()


async def test_process_turn_no_export_when_disabled(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="How has work been?")]}
    )
    settings = _settings(tmp_path, enabled=False)

    await process_turn("u1", CLOSING_MESSAGE, _Claude(), db, selector, settings)

    assert not (tmp_path / "personas").exists()
