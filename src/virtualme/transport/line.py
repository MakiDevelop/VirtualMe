import asyncio
import hashlib
import logging
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import BackgroundTasks, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    FlexMessage,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from virtualme.config import Settings
from virtualme.interview.bot import INTERVIEW_ERROR_REPLY, CrisisReply, process_turn
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB

logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
INTERVIEW_CLOSED_REPLY = "VirtualMe 目前為封閉測試, 尚未對外開放。"


async def handle_line_webhook(
    request: Request,
    claude: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
    channel_secret: str | None = None,
    settings: Settings | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> dict[str, Any]:
    settings = settings or Settings()
    body = await request.body()
    signature = request.headers.get("x-line-signature", "")
    secret = channel_secret or _secret_value(settings.line_channel_secret)
    access_token = _secret_value(settings.line_channel_access_token)

    if not secret or not access_token:
        logger.error("LINE webhook called without channel credentials")
        return {"status": "missing_line_credentials"}

    parser = WebhookParser(secret)
    try:
        events = parser.parse(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        logger.warning("LINE webhook rejected due to invalid signature")
        return {"status": "invalid_signature"}
    except Exception as exc:
        logger.warning("LINE webhook rejected due to malformed signature or body: %s", exc)
        return {"status": "invalid_signature"}

    queued = 0
    duplicate = 0
    skipped = 0
    for event in events:
        if not isinstance(event, MessageEvent):
            skipped += 1
            continue
        if not isinstance(event.message, TextMessageContent):
            skipped += 1
            continue
        if not event.reply_token:
            logger.warning("LINE text event skipped because reply_token is missing")
            skipped += 1
            continue

        interviewee_id = getattr(event.source, "user_id", None)
        if not interviewee_id:
            logger.warning("LINE text event skipped because user_id is missing")
            skipped += 1
            continue

        event_id = _event_id(event)
        message_id = getattr(event.message, "id", None)
        if event_id is None:
            logger.error("LINE text event skipped because stable event id is missing")
            skipped += 1
            continue
        if not await _can_access_interview(db, settings, interviewee_id):
            logger.info("LINE interview gate rejected new user: %s", interviewee_id)
            await _send_direct_text_reply(
                access_token,
                event.reply_token,
                interviewee_id,
                INTERVIEW_CLOSED_REPLY,
            )
            skipped += 1
            continue
        if not await db.claim_transport_event(
            event_id,
            "line",
            interviewee_id=interviewee_id,
            message_id=message_id,
        ):
            duplicate += 1
            logger.info("Duplicate LINE event skipped: %s", event_id)
            continue

        _enqueue(
            _process_text_event(
                event_id=event_id,
                reply_token=event.reply_token,
                interviewee_id=interviewee_id,
                incoming_message=event.message.text,
                access_token=access_token,
                claude=claude,
                db=db,
                selector=selector,
                settings=settings,
                download_base_url=_download_base_url(settings, request),
            ),
            background_tasks,
        )
        queued += 1

    return {"status": "ok", "queued": queued, "duplicate": duplicate, "skipped": skipped}


async def _can_access_interview(db: DB, settings: Settings, interviewee_id: str) -> bool:
    if settings.is_interview_user_allowed(interviewee_id):
        return True
    try:
        return await db.has_any_session(interviewee_id)
    except Exception as exc:
        logger.exception(
            "LINE interview gate session lookup failed for %s; rejecting access: %s",
            interviewee_id,
            exc,
        )
        return False


async def _send_direct_text_reply(
    access_token: str,
    reply_token: str,
    user_id: str,
    reply: str,
) -> bool:
    configuration = Configuration(access_token=access_token)
    async with AsyncApiClient(configuration) as api_client:
        return await _send_reply_or_push(
            AsyncMessagingApi(api_client),
            reply_token,
            user_id,
            reply,
        )


async def _process_text_event(
    *,
    event_id: str,
    reply_token: str,
    interviewee_id: str,
    incoming_message: str,
    access_token: str,
    claude: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
    settings: Settings,
    download_base_url: str | None = None,
) -> None:
    configuration = Configuration(access_token=access_token)
    async with AsyncApiClient(configuration) as api_client:
        line_bot_api = AsyncMessagingApi(api_client)
        try:
            reply = await process_turn(
                interviewee_id=interviewee_id,
                incoming_message=incoming_message,
                claude=claude,
                db=db,
                selector=selector,
                settings=settings,
                download_base_url=download_base_url,
            )
        except Exception as exc:
            logger.error("process_turn failed for %s: %s", interviewee_id, exc)
            await db.mark_transport_event_failed(event_id, str(exc))
            reply = INTERVIEW_ERROR_REPLY
        else:
            await db.mark_transport_event_done(event_id)
            if isinstance(reply, CrisisReply):
                await _push_crisis_alert(
                    line_bot_api,
                    settings,
                    interviewee_id,
                    reply,
                )
        await _send_reply_or_push(line_bot_api, reply_token, interviewee_id, reply)


async def _push_crisis_alert(
    line_bot_api: AsyncMessagingApi,
    settings: Settings,
    interviewee_id: str,
    reply: CrisisReply,
) -> None:
    alert_user_id = settings.crisis_alert_line_user_id
    if not alert_user_id:
        return

    interviewee_hash = hashlib.sha256(interviewee_id.encode()).hexdigest()[:8]
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    alert = f"crisis gate triggered {interviewee_hash} {timestamp} {reply.category.value}"
    try:
        await line_bot_api.push_message(
            PushMessageRequest(to=alert_user_id, messages=[TextMessage(text=alert)])
        )
    except Exception as exc:
        logger.error("Crisis alert push failed for %s: %s", interviewee_hash, exc)


async def _send_reply_or_push(
    line_bot_api: AsyncMessagingApi,
    reply_token: str,
    user_id: str,
    reply: str | dict,
) -> bool:
    token_hint = reply_token[:8]
    zip_path = getattr(reply, "zip_path", None)
    zip_caption = getattr(reply, "caption", None)
    if zip_path:
        logger.warning(
            "Persona zip artifact is ready for %s at %s, but LINE Messaging API "
            "does not support arbitrary file/zip send messages; sending text reply only.",
            user_id,
            zip_path,
        )

    # Support Flex Message (progress card etc.)
    if isinstance(reply, dict) and reply.get("type") == "flex":
        try:
            # More tolerant construction for different SDK versions
            flex_message = FlexMessage(
                alt_text=reply.get("altText", "訪談進度"),
                contents=reply["contents"],   # pass the bubble dict directly
            )
            await line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[flex_message])
            )
            logger.info("LINE Flex reply sent with token %s", token_hint)
            return True
        except Exception as flex_exc:
            logger.error("LINE Flex reply failed for %s: %s", user_id, flex_exc)
            # fallback to text
            reply = "目前進度卡片暫時無法顯示, 已切換為文字模式。"

    # Normal text path
    try:
        await line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=str(reply))],
            )
        )
        logger.info("LINE reply sent with token %s", token_hint)
        if zip_path and zip_caption:
            logger.info("Persona zip caption for %s: %s", user_id, zip_caption)
        return True
    except Exception as reply_exc:
        logger.error("LINE reply failed for %s with token %s: %s", user_id, token_hint, reply_exc)

    try:
        await line_bot_api.push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=str(reply))])
        )
        logger.info("LINE push fallback sent for %s after token %s failed", user_id, token_hint)
        return True
    except Exception as push_exc:
        logger.error("LINE push fallback failed for %s after token %s: %s", user_id, token_hint, push_exc)
        return False


def _secret_value(secret) -> str | None:
    return secret.get_secret_value() if secret is not None else None


def _download_base_url(settings: Settings, request: Request) -> str | None:
    if settings.persona_download_base_url:
        return settings.persona_download_base_url
    base_url = getattr(request, "base_url", None)
    return str(base_url).rstrip("/") if base_url is not None else None


def _event_id(event: MessageEvent) -> str | None:
    webhook_event_id = getattr(event, "webhook_event_id", None)
    message_id = getattr(event.message, "id", None)
    event_id = webhook_event_id or message_id
    return str(event_id) if event_id else None


def _enqueue(coro: Awaitable[None], background_tasks: BackgroundTasks | None) -> None:
    if background_tasks is not None:
        background_tasks.add_task(_await_background, coro)
        return
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _await_background(coro: Awaitable[None]) -> None:
    await coro
