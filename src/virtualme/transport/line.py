import base64
import hashlib
import hmac
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import HTTPException, Request

from virtualme.config import Settings
from virtualme.interview.bot import process_turn
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB


def verify_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    digest = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


async def handle_line_webhook(
    request: Request,
    claude: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
    channel_secret: str | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    body = await request.body()
    signature = request.headers.get("x-line-signature", "")
    if channel_secret and not verify_signature(body, signature, channel_secret):
        raise HTTPException(status_code=401, detail="invalid LINE signature")
    payload = await request.json()
    replies: list[dict[str, str]] = []
    for event in payload.get("events", []):
        message = event.get("message", {})
        if message.get("type") == "audio":
            replies.append({"status": "skipped", "reason": "audio download TODO"})
            continue
        if message.get("type") != "text":
            continue
        source = event.get("source", {})
        interviewee_id = source.get("userId") or "line-unknown"
        reply = await process_turn(interviewee_id, message.get("text", ""), claude, db, selector, settings)
        replies.append({"interviewee_id": interviewee_id, "reply": reply})
    return {"ok": True, "replies": replies}
