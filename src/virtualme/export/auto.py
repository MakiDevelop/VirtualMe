"""Auto-export the persona archive with local-only git versioning — BW6.

When an interview session closes *and* extraction is judged sufficient, the 8
dimension markdowns + manifest are re-exported into a per-subject folder and
committed to a git repo.

The repo is local-only by design: it is created with no remote and is never
pushed. Persona files stay on the machine (Chair directive: persona archives
must never reach a public remote). The export directory sits under ``data/``,
which the VirtualMe repo .gitignores, so this nested repo is invisible to it.

Git is invoked with asyncio's exec-file subprocess API: no shell is spawned and
every argument is passed as a list element, so there is no command-injection
surface even though interviewee_id flows into the argument list.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from virtualme.export.markdown import export_markdown
from virtualme.storage.db import DB

logger = logging.getLogger(__name__)

# Inline author keeps commits hermetic — no dependency on machine git config.
_GIT_AUTHOR = ["-c", "user.name=VirtualMe", "-c", "user.email=virtualme@localhost"]


async def auto_export_persona(db: DB, interviewee_id: str, export_dir: str) -> list[Path]:
    """Export the persona archive and commit it to a local-only git repo.

    The markdown export always runs. Git versioning is best-effort: a git
    failure is logged, never raised, so an odd git environment cannot break
    the interview reply.
    """
    _validate_interviewee_id(interviewee_id)
    base = Path(export_dir)
    base.mkdir(parents=True, exist_ok=True)
    written = await export_markdown(db, interviewee_id, base)
    await _commit_archive(base, interviewee_id)
    return written


def _validate_interviewee_id(interviewee_id: str) -> None:
    if (
        not interviewee_id
        or ".." in interviewee_id
        or "/" in interviewee_id
        or "\\" in interviewee_id
        or any(ord(char) < 32 for char in interviewee_id)
    ):
        raise ValueError("Invalid interviewee_id for persona export")


async def _run_git(repo: Path, *args: str) -> tuple[int, str]:
    """Run a git command via the shell-free exec-file subprocess API."""
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


async def _commit_archive(base: Path, interviewee_id: str) -> None:
    try:
        if not (base / ".git").is_dir():
            code, out = await _run_git(base, "init")
            if code != 0:
                logger.error("Persona repo git init failed: %s", out)
                return
        code, out = await _run_git(base, "remote")
        if code != 0:
            logger.error("Persona repo remote check failed: %s", out)
            return
        if out.strip():
            logger.error("Persona repo has remote configured; skipping local archive commit")
            return
        await _run_git(base, "add", "--", interviewee_id)
        # git diff --cached --quiet: exit 0 = nothing staged, 1 = staged changes.
        code, _ = await _run_git(base, "diff", "--cached", "--quiet")
        if code == 0:
            logger.info("Persona archive for %s unchanged; no commit", interviewee_id)
            return
        timestamp = datetime.now(UTC).isoformat(timespec="seconds")
        code, out = await _run_git(
            base,
            *_GIT_AUTHOR,
            "commit",
            "-m",
            f"persona 更新：{interviewee_id} @ {timestamp}",  # noqa: RUF001
        )
        if code != 0:
            logger.error("Persona archive commit failed for %s: %s", interviewee_id, out)
        else:
            logger.info("Persona archive committed for %s", interviewee_id)
    except Exception as exc:
        logger.error("Persona git versioning error for %s: %s", interviewee_id, exc)
