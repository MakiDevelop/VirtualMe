import json
import logging
from dataclasses import dataclass
from enum import StrEnum

from anthropic import AsyncAnthropic

from virtualme.interview.json_utils import extract_json_payload
from virtualme.interview.models import MODEL_FAST, create_message
from virtualme.storage.db import Layer

logger = logging.getLogger(__name__)
EVASION_CONFIDENCE_FLOOR = 0.85


class TurnKind(StrEnum):
    META = "META"
    EVASION = "EVASION"
    THIN = "THIN"
    SUFFICIENT = "SUFFICIENT"


@dataclass(frozen=True)
class TurnAssessment:
    kind: TurnKind
    depth: Layer
    needs_follow_up: bool
    confidence: float
    parse_failed: bool = False

    @property
    def value(self) -> str:
        return self.depth.value


async def evaluate_depth(
    answer: str, current_question: str, claude: AsyncAnthropic
) -> TurnAssessment:
    prompt = f"""
Assess this interview turn. Return JSON only, no markdown.

Schema:
{{
  "kind": "META" | "EVASION" | "THIN" | "SUFFICIENT",
  "depth": "fact" | "pattern" | "principle",
  "needs_follow_up": true | false,
  "confidence": 0.0-1.0
}}

Definitions:
- META: a question or comment about the interview itself (language, logistics,
  "why are you asking this", "can we switch topic") — not an answer to the topic.
- EVASION: ONLY explicit refusal or explicit topic deflection — e.g. "skip this",
  "I don't want to answer", "next question", "I don't want to talk about work".
  Do NOT classify as EVASION when the user expresses doubt, confusion, uncertainty,
  ambivalence, fatigue, sadness, frustration, or other difficult feelings ABOUT
  the asked topic — that is a genuine, often high-value answer. A self-directed
  rhetorical question can still be a real answer.
- THIN: answers the topic but too shallow to extract a stable persona signal alone.
- SUFFICIENT: answers with enough concrete, emotional, or value signal to extract
  anchors. Honest reflection about meaning, doubt, identity, or inner conflict is
  value signal.

Examples:
- Q: 請說說您最近的工作狀況。 A: 我有點迷惑, 有時我會覺得我的工作有價值嗎?
  => SUFFICIENT, needs_follow_up=true (honest reflection about work meaning)
- Q: 請說說您最近的工作狀況。 A: 最近很累, 有點不知道自己在忙什麼。
  => THIN, needs_follow_up=true (engaged but emotional / struggling)
- Q: 請說說您最近的工作狀況。 A: 跳過這題, 我想換一個。
  => EVASION (explicit refusal / deflection)

For META and EVASION, set needs_follow_up=false. Depth is only meaningful for
THIN/SUFFICIENT; use "fact" if not applicable.

Question: {current_question}
Answer: {answer}
"""
    response = await create_message(
        claude,
        model=MODEL_FAST,
        max_tokens=120,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    try:
        data = json.loads(extract_json_payload(raw))
        kind = TurnKind(str(data.get("kind", "")).upper())
        depth_text = str(data.get("depth", Layer.FACT.value)).lower()
        depth = Layer(depth_text if depth_text in {layer.value for layer in Layer} else Layer.FACT)
        confidence = float(data.get("confidence", 0))
        needs_follow_up = bool(data.get("needs_follow_up", False))
        if kind is TurnKind.EVASION and confidence < EVASION_CONFIDENCE_FLOOR:
            # 誤把真誠回答判成 EVASION 的代價(中斷訪談)遠大於誤把 evasion 當答案
            # (頂多多問一次)。低信心 EVASION 降級為可追問的 THIN。
            kind = TurnKind.THIN
            needs_follow_up = True
        return TurnAssessment(
            kind=kind,
            depth=depth,
            needs_follow_up=needs_follow_up,
            confidence=max(0.0, min(1.0, confidence)),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Turn assessment JSON parse failed: %s; raw=%r", exc, raw)
        return TurnAssessment(
            kind=TurnKind.SUFFICIENT,
            depth=Layer.FACT,
            needs_follow_up=False,
            confidence=0.0,
            parse_failed=True,
        )
