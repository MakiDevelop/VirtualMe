from enum import StrEnum

from anthropic import AsyncAnthropic

from virtualme.interview.lang import length_units, tokens
from virtualme.storage.db import Anchor, Layer


class FollowUpRule(StrEnum):
    R1_FACT_TO_PATTERN = "R1"
    R2_PATTERN_TO_PRINCIPLE = "R2"
    R3_PRINCIPLE_TO_COUNTEREXAMPLE = "R3"
    R4_ABSTRACT_TO_CONCRETE = "R4"
    R5_REPEAT_TO_TRIANGULATE = "R5"


ABSTRACT_MARKERS = {
    "honesty",
    "trust",
    "directness",
    "quality",
    "freedom",
    "respect",
    "誠實",
    "信任",
    "正直",
    "直接",
    "坦白",
    "品質",
    "自由",
    "尊重",
    "誠信",
    "真誠",
}


def select_rule(
    answer: str, depth: Layer, accumulated_anchors: list[Anchor]
) -> FollowUpRule | None:
    normalized = answer.lower()
    if any(marker in normalized for marker in ABSTRACT_MARKERS) and length_units(answer) <= 14:
        return FollowUpRule.R4_ABSTRACT_TO_CONCRETE
    if depth == Layer.FACT:
        return FollowUpRule.R1_FACT_TO_PATTERN
    if depth == Layer.PATTERN:
        return FollowUpRule.R2_PATTERN_TO_PRINCIPLE
    if depth != Layer.PRINCIPLE:
        return None
    if _has_triangulated_repeat(answer, accumulated_anchors):
        return FollowUpRule.R5_REPEAT_TO_TRIANGULATE
    return None if _has_concrete_example(answer) else FollowUpRule.R3_PRINCIPLE_TO_COUNTEREXAMPLE


async def generate_follow_up(
    rule: FollowUpRule, answer: str, original_question: str, claude: AsyncAnthropic
) -> str:
    if rule == FollowUpRule.R5_REPEAT_TO_TRIANGULATE:
        return "I think we have this principle clearly enough. Let me ask from another angle."
    prompt = f"""
Generate one short therapist-style follow-up question for rule {rule.value}.
Original question: {original_question}
Answer: {answer}
Keep their wording. Do not advise, praise, or explain.
"""
    response = await claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=80,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _has_triangulated_repeat(answer: str, anchors: list[Anchor]) -> bool:
    """Check if the answer represents a triangulated repeat.

    Triangulation requires the principle to be surfaced in at least 3 DIFFERENT questions,
    not just 3 turns. We count unique source_question_ids to enforce this.
    """
    words = set(tokens(answer))
    for anchor in anchors:
        if anchor.layer != Layer.PRINCIPLE:
            continue
        overlap = words & set(tokens(anchor.content))
        if len(overlap) < 4:
            continue
        # Count unique question IDs — triangulation needs 3 different questions
        unique_questions = set(anchor.source_question_ids)
        if len(unique_questions) >= 3:
            return True
    return False


def _has_concrete_example(answer: str) -> bool:
    lowered = answer.lower()
    markers = (
        "once",
        "yesterday",
        "last ",
        "when ",
        "client",
        "manager",
        "case",
        "有一次",
        "上次",
        "之前",
        "那時",
        "當時",
        "客戶",
        "主管",
        "案子",
        "記得",
    )
    return any(marker in lowered for marker in markers)
