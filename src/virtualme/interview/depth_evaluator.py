import json
import logging
from dataclasses import dataclass
from enum import StrEnum

from anthropic import AsyncAnthropic

from virtualme.interview.json_utils import extract_json_payload
from virtualme.interview.models import MODEL_FAST, create_message
from virtualme.storage.db import Layer

logger = logging.getLogger(__name__)


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
- META: language/logistics/meta question about the interview, not an answer.
- EVASION: refusal, complaint, annoyance, or avoiding the question.
- THIN: answers the question but too shallow to extract a stable persona signal alone.
- SUFFICIENT: answers with enough concrete or value signal to extract anchors.

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
        return TurnAssessment(
            kind=kind,
            depth=depth,
            needs_follow_up=bool(data.get("needs_follow_up", False)),
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
