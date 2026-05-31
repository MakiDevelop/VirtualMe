from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from virtualme.storage.db import DB


class DownloadTokenError(Exception):
    """Base error for persona download token failures."""


class DownloadTokenNotFound(DownloadTokenError):
    """Token does not exist."""


class DownloadTokenExpired(DownloadTokenError):
    """Token exists but expired."""


class DownloadFileUnavailable(DownloadTokenError):
    """Token is valid, but the zip path is unavailable or unsafe."""


@dataclass(frozen=True)
class DownloadTokenRecord:
    token_hash: str
    interviewee_id: str
    zip_path: Path
    expires_at: datetime


def build_download_url(base_url: str, raw_token: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/download/persona/{raw_token}"


async def create_download_token(
    db: DB,
    interviewee_id: str,
    zip_path: Path,
    *,
    expiry_minutes: int = 60,
    now: datetime | None = None,
) -> str:
    resolved_zip = zip_path.resolve()
    if not resolved_zip.is_file():
        raise DownloadFileUnavailable(f"persona zip does not exist: {resolved_zip}")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    created_at = _utc_now(now)
    expires_at = created_at + timedelta(minutes=expiry_minutes)

    await db.init()
    async with db._connect() as conn:
        await conn.execute(
            """
            INSERT INTO persona_download_tokens(
                token_hash, interviewee_id, zip_path, created_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                token_hash,
                interviewee_id,
                str(resolved_zip),
                _format_time(created_at),
                _format_time(expires_at),
            ),
        )
        await conn.commit()
    return raw_token


async def resolve_download_token(
    db: DB,
    raw_token: str,
    *,
    persona_export_dir: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> DownloadTokenRecord:
    token_hash = hash_token(raw_token)
    requested_at = _utc_now(now)
    await db.init()
    async with db._connect() as conn:
        conn.row_factory = None
        row = await (
            await conn.execute(
                """
                SELECT token_hash, interviewee_id, zip_path, expires_at
                FROM persona_download_tokens
                WHERE token_hash = ?
                """,
                (token_hash,),
            )
        ).fetchone()
        if row is None:
            await _insert_download_log(
                conn,
                token_hash=token_hash,
                requested_at=requested_at,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                failure_reason="token_not_found",
            )
            await conn.commit()
            raise DownloadTokenNotFound("persona download token not found")

        row_token_hash, interviewee_id, zip_path, expires_at = row
        parsed_expiry = _parse_time(expires_at)
        if parsed_expiry <= requested_at:
            await _insert_download_log(
                conn,
                token_hash=token_hash,
                interviewee_id=interviewee_id,
                requested_at=requested_at,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                failure_reason="token_expired",
                zip_path=zip_path,
            )
            await conn.commit()
            raise DownloadTokenExpired("persona download token expired")

        resolved_zip = _safe_zip_path(Path(zip_path), Path(persona_export_dir))
        if resolved_zip is None or not resolved_zip.is_file():
            await _insert_download_log(
                conn,
                token_hash=token_hash,
                interviewee_id=interviewee_id,
                requested_at=requested_at,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                failure_reason="zip_unavailable",
                zip_path=zip_path,
            )
            await conn.commit()
            raise DownloadFileUnavailable("persona zip unavailable")

        await conn.execute(
            """
            UPDATE persona_download_tokens
            SET download_count = download_count + 1,
                last_downloaded_at = ?
            WHERE token_hash = ?
            """,
            (_format_time(requested_at), token_hash),
        )
        await _insert_download_log(
            conn,
            token_hash=token_hash,
            interviewee_id=interviewee_id,
            requested_at=requested_at,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
            zip_path=str(resolved_zip),
        )
        await conn.commit()

    return DownloadTokenRecord(
        token_hash=row_token_hash,
        interviewee_id=interviewee_id,
        zip_path=resolved_zip,
        expires_at=parsed_expiry,
    )


async def cleanup_expired_download_tokens(
    db: DB,
    *,
    now: datetime | None = None,
) -> int:
    cutoff = _format_time(_utc_now(now))
    await db.init()
    async with db._connect() as conn:
        cursor = await conn.execute(
            "DELETE FROM persona_download_tokens WHERE expires_at < ?",
            (cutoff,),
        )
        await conn.commit()
        return cursor.rowcount or 0


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def _insert_download_log(
    conn,
    *,
    token_hash: str,
    requested_at: datetime,
    success: bool,
    interviewee_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    failure_reason: str | None = None,
    zip_path: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO persona_download_logs(
            interviewee_id, token_hash, requested_at, ip_address, user_agent,
            success, failure_reason, zip_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            interviewee_id,
            token_hash,
            _format_time(requested_at),
            ip_address,
            user_agent,
            1 if success else 0,
            failure_reason,
            zip_path,
        ),
    )


def _safe_zip_path(zip_path: Path, export_dir: Path) -> Path | None:
    resolved = zip_path.resolve()
    base = export_dir.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return None
    if resolved.suffix.lower() != ".zip":
        return None
    return resolved


def _utc_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    return now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _parse_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
