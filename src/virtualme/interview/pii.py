"""Regex-only PII scrubbing for interview turns.

VirtualMe stores interview transcripts as durable memory seeds, so obvious personal data must
be removed before it can enter prompts, anchors, or triple extraction. This module deliberately
uses local regular expressions only: it is cheap, deterministic, dependency-free, and never sends
raw text to a network classifier. The trade-off is lower recall than a real NER pipeline; v0.5 can
replace or augment these heuristics if real interviews show too many misses.

Known limitations: regexes will miss names without clear capitalization, unusual romanization,
nicknames, company aliases without suffixes, and dates written in vague natural language. They may
also over-redact title-cased phrases that are not people.

Known PII categories we do NOT catch:
- Diminutive names or nicknames such as "Johnny", "A-san", or "阿明".
- Emoji-fragmented text such as "John 🤖 Smith".
- Multilingual fragments mixing scripts inside one name.
- Addresses, schools, hospitals, and team names without company suffixes.
- Social handles, bank accounts, passport numbers, and tax IDs outside Taiwan.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Redaction(BaseModel):
    category: str
    original: str
    replacement: str
    span: tuple[int, int]


class ScrubResult(BaseModel):
    scrubbed_text: str
    redactions: list[Redaction]


MatchReplacement = Callable[[re.Match[str], dict[str, str]], tuple[str, str]]

PLACEHOLDER_RE = re.compile(
    r"\[(?:Person [A-Z]|Company [A-Z]|EMAIL|PHONE|TW_ID|Salary [^\]]+|Age \d0s|Birthday [^\]]+)\]"
)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+?886[- ]?)?0?9\d{2}[- ]?\d{3}[- ]?\d{3}\b")
TW_ID_RE = re.compile(r"\b[A-Z]\d{9}\b", re.IGNORECASE)
SALARY_RE = re.compile(r"\b(\d{2,3})(?:,?000|k)?(?:\s*-\s*(\d{2,3})(?:,?000|k)?)?\b", re.I)
AGE_RE = re.compile(r"\b(?:aged\s*)?(\d{1,2})\s*(?:歲|years?\s*old)\b", re.I)
BIRTHDAY_RE = re.compile(
    r"\b(?:\d{4}[-/])?(\d{1,2})[-/]\d{1,2}\b"
    r"|\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\s+\d{1,2}\b",
    re.I,
)
EN_PERSON_RE = re.compile(r"\b([A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,})+)\b")
ZH_PERSON_RE = re.compile(
    r"(?<![\u4e00-\u9fff])"
    r"([王李張陳林黃吳劉蔡楊許鄭謝郭洪曾邱廖賴徐周葉蘇莊呂江何蕭羅高潘簡朱鍾游詹沈彭胡余盧][\u4e00-\u9fff]{1,2})"
    r"(?![\u4e00-\u9fff])"
)
COMPANY_RE = re.compile(
    r"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,3}\s+"
    r"(?:Inc|Corp|Corporation|LLC|Ltd|Limited|Company))\b"
    r"|([\u4e00-\u9fff]{2,8}(?:公司|股份有限公司))",
    re.I,
)


def scrub_pii(text: str) -> ScrubResult:
    if not text or not text.strip():
        return ScrubResult(scrubbed_text=text, redactions=[])

    aliases: dict[str, str] = {}
    redactions: list[Redaction] = []
    replacements: list[tuple[int, int, str, str, str]] = []
    occupied = [match.span() for match in PLACEHOLDER_RE.finditer(text)]

    specs: list[tuple[str, re.Pattern[str], MatchReplacement]] = [
        ("email", EMAIL_RE, lambda _match, _aliases: ("[EMAIL]", "email")),
        ("phone", PHONE_RE, lambda _match, _aliases: ("[PHONE]", "phone")),
        ("tw_id", TW_ID_RE, lambda _match, _aliases: ("[TW_ID]", "tw_id")),
        ("birthday", BIRTHDAY_RE, _birthday_replacement),
        ("age", AGE_RE, _age_replacement),
        ("salary", SALARY_RE, _salary_replacement),
        ("company", COMPANY_RE, _company_replacement),
        ("person", EN_PERSON_RE, _person_replacement),
        ("person", ZH_PERSON_RE, _person_replacement),
    ]

    for category, pattern, replacement_for in specs:
        for match in pattern.finditer(text):
            if _overlaps(match.span(), occupied):
                continue
            replacement, normalized_category = replacement_for(match, aliases)
            if not replacement:
                continue
            start, end = match.span()
            replacements.append((start, end, replacement, normalized_category or category, match.group(0)))
            occupied.append((start, end))

    replacements.sort(key=lambda item: item[0])
    if not replacements:
        return ScrubResult(scrubbed_text=text, redactions=[])

    redacted_chars = sum(end - start for start, end, *_ in replacements)
    if len(replacements) >= 3 and redacted_chars > len(text) * 0.5:
        logger.warning("PII scrub skipped because redactions exceeded 50 percent of input length")
        return ScrubResult(scrubbed_text=text, redactions=[])

    cursor = 0
    chunks: list[str] = []
    for start, end, replacement, category, original in replacements:
        chunks.append(text[cursor:start])
        chunks.append(replacement)
        redactions.append(
            Redaction(
                category=category,
                original=original,
                replacement=replacement,
                span=(start, end),
            )
        )
        cursor = end
    chunks.append(text[cursor:])
    return ScrubResult(scrubbed_text="".join(chunks), redactions=redactions)


def detect_pii(text: str) -> list[str]:
    return [redaction.category for redaction in scrub_pii(text).redactions]


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < used_end and end > used_start for used_start, used_end in occupied)


def _person_replacement(match: re.Match[str], aliases: dict[str, str]) -> tuple[str, str]:
    return (_alias(match.group(1), aliases, "person", "Person", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")), "person")


def _company_replacement(match: re.Match[str], aliases: dict[str, str]) -> tuple[str, str]:
    original = match.group(1) or match.group(2)
    codes = ["H", "J", "K", "L", "M", "N", "P", "Q", "R", "S"]
    return (_alias(original, aliases, "company", "Company", codes), "company")


def _alias(original: str, aliases: dict[str, str], namespace: str, label: str, codes: list[str]) -> str:
    key = f"{namespace}:{original.lower()}"
    if key not in aliases:
        aliases[key] = f"[{label} {codes[min(len([k for k in aliases if k.startswith(namespace)]), len(codes) - 1)]}]"
    return aliases[key]


def _salary_replacement(match: re.Match[str], _aliases: dict[str, str]) -> tuple[str, str]:
    raw = match.group(0).lower().replace(",", "")
    # A bare numeric range (e.g. "100-150") is too ambiguous to treat as salary:
    # it is just as likely a count, score, or page range. Require an explicit
    # magnitude marker (k / 000); ranges like "80k-100k" still qualify.
    if not ("k" in raw or "000" in raw):
        return ("", "salary")
    low = _salary_to_k(match.group(1), raw)
    high = _salary_to_k(match.group(2), raw) if match.group(2) else low
    low_bucket = max(0, (min(low, high) // 20) * 20)
    high_bucket = max(low_bucket + 20, ((max(low, high) + 19) // 20) * 20)
    return (f"[Salary {low_bucket}-{high_bucket}k]", "salary")


def _salary_to_k(value: str | None, raw: str) -> int:
    if not value:
        return 0
    amount = int(value)
    return amount if "k" in raw or amount < 1000 else amount // 1000


def _age_replacement(match: re.Match[str], _aliases: dict[str, str]) -> tuple[str, str]:
    age = int(match.group(1))
    return (f"[Age {(age // 10) * 10}s]", "age")


def _birthday_replacement(match: re.Match[str], _aliases: dict[str, str]) -> tuple[str, str]:
    month = match.group(1) or match.group(2)
    if month and month.isdigit():
        month = f"{int(month):02d}"
    return (f"[Birthday {month.lower()}]", "birthday")
