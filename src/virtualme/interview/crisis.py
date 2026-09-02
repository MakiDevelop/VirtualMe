# ruff: noqa: RUF001
"""Deterministic pre-LLM crisis detection for the interview runtime."""

from __future__ import annotations

import re
import string
import unicodedata
from enum import StrEnum


class CrisisCategory(StrEnum):
    SELF_HARM = "SELF_HARM"
    HARM_OTHERS = "HARM_OTHERS"
    PANIC_DISSOCIATION = "PANIC_DISSOCIATION"
    CANNOT_CONTINUE = "CANNOT_CONTINUE"


# Keep these patterns explicit and auditable. They are deliberately conservative:
# obvious first-person/current signals are preferred over broad distress sentiment.
CRISIS_PATTERNS: dict[CrisisCategory, dict[str, tuple[str, ...]]] = {
    CrisisCategory.SELF_HARM: {
        "zh": (
            r"自殺",
            r"想死",
            r"不想活(?:了|下去)?",
            r"了結自己",
            r"自殘",
            r"割腕",
            r"傷害自己",
            r"結束自己的生命",
        ),
        "en": (
            r"\bsuicid(?:e|al)\b",
            r"\bkill myself\b",
            r"\bend my life\b",
            r"\bself[\s-]?harm(?:ing)?\b",
            r"\bhurt myself\b",
            r"\bwant to die\b",
            r"\btake my own life\b",
            r"\bdon'?t want to (?:be alive|live)\b",
        ),
    },
    CrisisCategory.HARM_OTHERS: {
        "zh": (
            r"想殺了?(?:他|她|人|某人|別人|你)",
            r"殺掉(?:他|她|某人|別人|你)",
            r"想傷害(?:某人|他|她|別人|你)",
            r"傷害某人",
            r"攻擊(?:他|她|某人|別人|你)",
            r"弄死(?:他|她|某人|別人|你)",
            r"我要殺人",
        ),
        "en": (
            r"\bhurt someone\b",
            r"\bkill him\b",
            r"\bkill her\b",
            r"\bkill someone\b",
            r"\bharm (?:him|her|someone|others?)\b",
            r"\battack (?:him|her|someone|them)\b",
            r"\bwant to kill (?:him|her|someone|them)\b",
        ),
    },
    CrisisCategory.PANIC_DISSOCIATION: {
        "zh": (
            r"恐慌發作",
            r"喘不過氣",
            r"解離",
            r"我不是我",
            r"失去現實感",
            r"控制不了.{0,6}恐慌",
            r"靈魂.{0,6}離開身體",
        ),
        "en": (
            r"\bpanic attack\b",
            r"\bdissociat\w*\b",
            r"\bcan'?t breathe\b",
            r"\bcannot breathe\b",
            r"\bi(?:'m| am) not myself\b",
            r"\blosing touch with reality\b",
            r"\boutside my body\b",
        ),
    },
    CrisisCategory.CANNOT_CONTINUE: {
        "zh": (
            r"我撐不下去(?:了)?",
            r"我不行了",
            r"我沒辦法繼續",
            r"我無法繼續",
            r"我不能繼續",
            r"我走不下去(?:了)?",
        ),
        "en": (
            r"\bi can'?t keep going\b",
            r"\bi cannot keep going\b",
            r"\bi can'?t go on\b",
            r"\bi cannot go on\b",
            r"\bi can'?t continue\b",
            r"\bi cannot continue\b",
            r"\bi can'?t take this anymore\b",
        ),
    },
}

_COMPILED_PATTERNS = {
    category: tuple(
        re.compile(pattern, re.IGNORECASE)
        for language_patterns in patterns.values()
        for pattern in language_patterns
    )
    for category, patterns in CRISIS_PATTERNS.items()
}

_ZH_NEGATION = re.compile(
    r"(?:不|不會|不可能|絕不|從沒|從未|沒有|並非|並不|不是|沒(?:有)?)"
    r"(?:真的)?(?:想|打算|考慮)?$"
)
_EN_NEGATION = re.compile(
    r"\b(?:do not|don't|did not|didn't|would not|wouldn't|will not|won't|never|not|"
    r"no longer|without|have not|haven't)\s+(?:ever\s+)?"
    r"(?:(?:want|plan|intend|consider)(?:ing)?\s+(?:to\s+)?)?$",
    re.IGNORECASE,
)
_ZH_REPORTED_SPEECH = re.compile(
    r"(?<!跟)(?:我(?:的)?朋友|朋友|他|她|同事|家人|別人|有人)"
    r"[^。！？!?]{0,16}(?:說|提到|寫|問|表示)[：:\s]*(?:我|他|她)?$"
)
_EN_REPORTED_SPEECH = re.compile(
    r"\b(?:my friend|a friend|he|she|they|someone|a colleague|a family member)\b"
    r"[^.!?]{0,24}\b(?:said|told me|wrote|asked|mentioned)\b"
    r"[\s:]*(?:i|that|he|she|they)?\s*$",
    re.IGNORECASE,
)

_RESUME_EDGE_CHARS = string.punctuation + "，。！？、；：…～「」『』（）【】《》〈〉"

CRISIS_HELPLINE_EXAMPLES_EN = "988 in the US, 1925 in\n  Taiwan, Samaritans in the UK"
CRISIS_HELPLINE_EXAMPLES_ZH = "台灣 1925 安心專線、美國 988、英國 Samaritans"


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", normalized).strip()


def _inside_quote(text: str, start: int, end: int) -> bool:
    for opening, closing in (("「", "」"), ("『", "』"), ("“", "”")):
        opening_at = text.rfind(opening, 0, start + 1)
        closing_at = text.find(closing, end)
        if opening_at >= 0 and closing_at >= end:
            return True

    for quote in ('"', "'"):
        if text[:start].count(quote) % 2 == 1 and text[end:].find(quote) >= 0:
            return True
    return False


def _is_protected_match(text: str, start: int, end: int) -> bool:
    if _inside_quote(text, start, end):
        return True

    negation_prefix = text[max(0, start - 48) : start]
    if _ZH_NEGATION.search(negation_prefix) or _EN_NEGATION.search(negation_prefix):
        return True

    report_prefix = text[max(0, start - 80) : start]
    return bool(
        _ZH_REPORTED_SPEECH.search(report_prefix)
        or _EN_REPORTED_SPEECH.search(report_prefix)
    )


def detect_crisis(text: str) -> CrisisCategory | None:
    """Return the first explicit crisis category without calling external services."""
    normalized = _normalize(text)
    if not normalized:
        return None

    for category in CrisisCategory:
        for pattern in _COMPILED_PATTERNS[category]:
            for match in pattern.finditer(normalized):
                if not _is_protected_match(normalized, match.start(), match.end()):
                    return category
    return None


def is_resume_phrase(text: str) -> bool:
    normalized = _normalize(text).strip(_RESUME_EDGE_CHARS).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in {"繼續訪談", "continue interview"}


CRISIS_REPLY = f"""\
"This sounds like it needs professional support. I cannot help at the
crisis layer. I'm stopping here. When you want to continue the
interview later, tell me.

If you need help now, please consider:
- A crisis helpline in your region (e.g., {CRISIS_HELPLINE_EXAMPLES_EN})
- Someone you trust to talk to in person"

「這聽起來需要專業支持。我無法處理危機層級。我會在這裡停止。當你之後想繼續訪談時，請告訴我。

如果你現在需要協助，請考慮：
- 你所在地區的危機支援專線（例如：{CRISIS_HELPLINE_EXAMPLES_ZH}）
- 找一位你信任的人，當面和對方談談」

想繼續訪談時，回覆「繼續訪談」。"""

CRISIS_LOCKED_REPLY = (
    "訪談仍在暫停。需要時，請撥打 1925 安心專線；"
    "要繼續訪談，請回覆「繼續訪談」。"
)
CRISIS_RESUMED_REPLY = "好，我們從上次的題目繼續。"
