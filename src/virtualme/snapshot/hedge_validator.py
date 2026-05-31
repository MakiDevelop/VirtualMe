"""Hedge wording validator — Constitution v1.1 §P5 hard gate.

Detects unhedged stable-trait assertions in synthesis/export output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORBIDDEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b[Yy]ou are (an? )?[A-Za-z][A-Za-z -]+\b"),
    re.compile(r"\b[Yy]our true (self|nature) is\b"),
    re.compile(r"\b[Yy]ou always\b"),
    re.compile(r"\b[Yy]ou never\b"),
    re.compile(r"你是個?[一-鿿]+的人"),
    re.compile(r"你的本質是"),
    re.compile(r"你的真實面是?"),
    re.compile(r"你總是[一-鿿]+"),
]

HEDGE_MARKERS: list[str] = [
    "目前觀察到",
    "根據訪談",
    "可能",
    "傾向",
    "似乎",
    "tentative",
    "draft",
    "hypothesis",
    "appears to",
    "tends to",
    "in W",
    "在 W",
]


@dataclass(frozen=True)
class HedgeViolation:
    line_number: int
    matched_text: str
    pattern_id: int


class HedgeValidationError(ValueError):
    def __init__(self, surface: str, violations: list[HedgeViolation]) -> None:
        self.surface = surface
        self.violations = violations
        details = ", ".join(
            f"line {violation.line_number}: {violation.matched_text}"
            for violation in violations[:3]
        )
        super().__init__(f"{surface} contains unhedged stable assertions: {details}")


def find_unhedged_assertions(
    text: str,
    *,
    ignore_markdown_blockquotes: bool = False,
) -> list[HedgeViolation]:
    """Return forbidden stable-trait assertions found in text."""
    violations: list[HedgeViolation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if ignore_markdown_blockquotes and line.lstrip().startswith(">"):
            continue
        for pattern_id, pattern in enumerate(FORBIDDEN_PATTERNS):
            match = pattern.search(line)
            if match:
                violations.append(
                    HedgeViolation(
                        line_number=line_number,
                        matched_text=match.group(0),
                        pattern_id=pattern_id,
                    )
                )
    return violations


def has_hedge_marker(text: str) -> bool:
    """Return True when text includes at least one known hedge marker."""
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in HEDGE_MARKERS)


def assert_no_unhedged_assertions(
    text: str,
    *,
    surface: str,
    ignore_markdown_blockquotes: bool = True,
) -> None:
    """Fail before writing generated surfaces with unhedged stable assertions."""
    violations = find_unhedged_assertions(
        text,
        ignore_markdown_blockquotes=ignore_markdown_blockquotes,
    )
    if violations:
        raise HedgeValidationError(surface, violations)
