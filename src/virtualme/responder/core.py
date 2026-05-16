"""Responder core: turn an incoming message into a persona-voiced reply."""

from __future__ import annotations

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from virtualme.config import Settings
from virtualme.interview.models import MODEL_STANDARD
from virtualme.responder.liability import is_liability_topic

DISCLOSURE_FOOTER = "\n\n— 本訊息由 AI 助理依本人風格草擬, 僅供參考。"
LIABILITY_NUDGE = "\n\n⚠️ 這題涉及權責判斷, 請務必再向本人確認後再依循。"


class ResponderResult(BaseModel):
    reply: str
    is_liability: bool


async def respond(
    incoming_message: str,
    persona_context: str,
    claude: AsyncAnthropic,
    settings: Settings | None = None,
) -> ResponderResult:
    settings = settings or Settings()
    liability = is_liability_topic(incoming_message)
    system = (
        "你是一位 HR/HRBP 顧問的 AI 助理, 請用她的口吻與專業風格回答提問。\n"
        "人格與風格參考:\n"
        f"{persona_context}\n\n"
        "規則:\n"
        "- 若對方問你是不是真人, 誠實說明你是 AI 助理。\n"
        "- 不代表本人做出任何承諾、決定或保證。\n"
        "- 回答簡潔、專業、貼近她的語氣。\n"
        "- 涉及法律或權責的問題, 給方向但提醒對方須向本人確認。"
    )
    response = await claude.messages.create(
        model=MODEL_STANDARD,
        max_tokens=600,
        temperature=0.4,
        system=system,
        messages=[{"role": "user", "content": incoming_message}],
    )
    reply = response.content[0].text.strip()
    if liability:
        reply = f"{reply}{LIABILITY_NUDGE}"
    reply = f"{reply}{DISCLOSURE_FOOTER}"
    return ResponderResult(reply=reply, is_liability=liability)
