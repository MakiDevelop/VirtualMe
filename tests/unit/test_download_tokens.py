from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite
import pytest

from virtualme.export.download_tokens import (
    DownloadFileUnavailable,
    DownloadTokenExpired,
    build_download_url,
    cleanup_expired_download_tokens,
    create_download_token,
    hash_token,
    resolve_download_token,
)
from virtualme.storage.db import DB


async def _new_db(tmp_path: Path) -> DB:
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    return db


async def _download_count(db: DB, raw_token: str) -> int:
    async with aiosqlite.connect(db.path) as conn:
        row = await (
            await conn.execute(
                "SELECT download_count FROM persona_download_tokens WHERE token_hash = ?",
                (hash_token(raw_token),),
            )
        ).fetchone()
    return int(row[0])


async def _log_rows(db: DB) -> list[tuple]:
    async with aiosqlite.connect(db.path) as conn:
        rows = await (
            await conn.execute(
                "SELECT success, failure_reason, ip_address, user_agent FROM persona_download_logs"
            )
        ).fetchall()
    return rows


async def test_create_and_resolve_download_token_allows_repeat_downloads(tmp_path):
    db = await _new_db(tmp_path)
    export_dir = tmp_path / "personas"
    zip_path = export_dir / "_packages" / "u1" / "VirtualMe_人格檔_20260520.zip"
    zip_path.parent.mkdir(parents=True)
    zip_path.write_bytes(b"zip")

    raw_token = await create_download_token(db, "u1", zip_path)
    first = await resolve_download_token(
        db,
        raw_token,
        persona_export_dir=str(export_dir),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    second = await resolve_download_token(db, raw_token, persona_export_dir=str(export_dir))

    assert first.zip_path == zip_path.resolve()
    assert second.interviewee_id == "u1"
    assert await _download_count(db, raw_token) == 2
    assert (1, None, "127.0.0.1", "pytest") in await _log_rows(db)


async def test_resolve_expired_download_token_records_failure(tmp_path):
    db = await _new_db(tmp_path)
    export_dir = tmp_path / "personas"
    zip_path = export_dir / "_packages" / "u1" / "VirtualMe_人格檔_20260520.zip"
    zip_path.parent.mkdir(parents=True)
    zip_path.write_bytes(b"zip")
    created_at = datetime(2026, 5, 20, 1, 0, tzinfo=UTC)
    raw_token = await create_download_token(db, "u1", zip_path, now=created_at)

    with pytest.raises(DownloadTokenExpired):
        await resolve_download_token(
            db,
            raw_token,
            persona_export_dir=str(export_dir),
            now=created_at + timedelta(minutes=61),
        )

    assert (0, "token_expired", None, None) in await _log_rows(db)


async def test_resolve_rejects_zip_outside_export_dir(tmp_path):
    db = await _new_db(tmp_path)
    export_dir = tmp_path / "personas"
    outside_zip = tmp_path / "other" / "secret.zip"
    outside_zip.parent.mkdir()
    outside_zip.write_bytes(b"zip")
    raw_token = await create_download_token(db, "u1", outside_zip)

    with pytest.raises(DownloadFileUnavailable):
        await resolve_download_token(db, raw_token, persona_export_dir=str(export_dir))

    assert (0, "zip_unavailable", None, None) in await _log_rows(db)


async def test_cleanup_expired_download_tokens(tmp_path):
    db = await _new_db(tmp_path)
    export_dir = tmp_path / "personas"
    zip_path = export_dir / "_packages" / "u1" / "VirtualMe_人格檔_20260520.zip"
    zip_path.parent.mkdir(parents=True)
    zip_path.write_bytes(b"zip")
    created_at = datetime(2026, 5, 20, 1, 0, tzinfo=UTC)
    await create_download_token(db, "u1", zip_path, now=created_at)

    deleted = await cleanup_expired_download_tokens(
        db,
        now=created_at + timedelta(minutes=61),
    )

    assert deleted == 1


def test_build_download_url_normalizes_base():
    assert build_download_url("https://vm.example.com/", "abc") == (
        "https://vm.example.com/download/persona/abc"
    )
