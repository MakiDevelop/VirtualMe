import logging
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from virtualme.config import Settings
from virtualme.interview.bot import INTERVIEW_ERROR_REPLY, process_turn
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB

logger = logging.getLogger(__name__)


async def handle_line_webhook(
    request: Request,
    claude: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
    channel_secret: str | None = None,
    settings: Settings | None = None,
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

    configuration = Configuration(access_token=access_token)
    handled = 0
    async with AsyncApiClient(configuration) as api_client:
        line_bot_api = AsyncMessagingApi(api_client)
        for event in events:
            if not isinstance(event, MessageEvent):
                continue
            if not isinstance(event.message, TextMessageContent):
                continue
            if not event.reply_token:
                logger.warning("LINE text event skipped because reply_token is missing")
                continue

            interviewee_id = getattr(event.source, "user_id", None)
            if not interviewee_id:
                logger.warning("LINE text event skipped because user_id is missing")
                continue

            try:
                reply = await process_turn(
                    interviewee_id=interviewee_id,
                    incoming_message=event.message.text,
                    claude=claude,
                    db=db,
                    selector=selector,
                    settings=settings,
                )
            except Exception as exc:
                logger.error("process_turn failed for %s: %s", interviewee_id, exc)
                reply = INTERVIEW_ERROR_REPLY
            if await _send_reply_or_push(line_bot_api, event.reply_token, interviewee_id, reply):
                handled += 1

    return {"status": "ok", "handled": handled}


async def _send_reply_or_push(
    line_bot_api: AsyncMessagingApi,
    reply_token: str,
    user_id: str,
    reply: str,
) -> bool:
    token_hint = reply_token[:8]
    try:
        await line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=reply)],
            )
        )
        logger.info("LINE reply sent with token %s", token_hint)
        return True
    except Exception as reply_exc:
        logger.error("LINE reply failed for %s with token %s: %s", user_id, token_hint, reply_exc)

    try:
        await line_bot_api.push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=reply)])
        )
        logger.info("LINE push fallback sent for %s after token %s failed", user_id, token_hint)
        return True
    except Exception as push_exc:
        logger.error("LINE push fallback failed for %s after token %s: %s", user_id, token_hint, push_exc)
        return False


def _secret_value(secret) -> str | None:
    return secret.get_secret_value() if secret is not None else None
