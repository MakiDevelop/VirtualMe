"""CJK-aware text helpers for the interview engine.

The follow-up router, question selector, and PPA retrieval all reason about
answer length and token overlap. The original heuristics used str.split() and
an a-z regex, which silently degrade to a near no-op for Chinese/Japanese
answers (no whitespace word boundaries). These helpers give one tokenisation
that works for both Latin and CJK text: Latin words stay whole, CJK runs
become character bigrams.
"""

from __future__ import annotations

import re

CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]+")
LATIN_RE = re.compile(r"[a-z0-9_]+")


def tokens(text: str) -> list[str]:
    """Tokenise mixed Latin/CJK text for overlap and similarity checks.

    Latin runs become lowercase word tokens. CJK runs become character
    bigrams (a single character if the run has length 1). Bigrams give a
    meaningful cosine/overlap signal for languages without word spaces.
    """
    lowered = text.lower()
    result: list[str] = list(LATIN_RE.findall(lowered))
    for run in CJK_RE.findall(lowered):
        if len(run) == 1:
            result.append(run)
        else:
            result.extend(run[i : i + 2] for i in range(len(run) - 1))
    return result


def length_units(text: str) -> int:
    """Approximate how long an answer is across scripts.

    Each Latin word counts as 1; each CJK character counts as 1. Used by the
    follow-up router's short-abstract-answer threshold. This is intentionally
    an approximation: a precise cross-script length is not needed here.
    """
    latin = len(LATIN_RE.findall(text.lower()))
    cjk = sum(len(run) for run in CJK_RE.findall(text))
    return latin + cjk
