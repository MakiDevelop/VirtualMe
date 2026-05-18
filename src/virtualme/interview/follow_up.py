from enum import StrEnum

from anthropic import AsyncAnthropic

from virtualme.interview.lang import INTERVIEW_OUTPUT_LANGUAGE, length_units, tokens
from virtualme.interview.models import MODEL_STANDARD, create_message
from virtualme.storage.db import Anchor, Layer


class FollowUpRule(StrEnum):
    R1_FACT_TO_PATTERN = "R1"
    R2_PATTERN_TO_PRINCIPLE = "R2"
    R3_PRINCIPLE_TO_COUNTEREXAMPLE = "R3"
    R4_ABSTRACT_TO_CONCRETE = "R4"
    R5_REPEAT_TO_TRIANGULATE = "R5"


FOLLOW_UP_RULE_PROMPTS = {
    FollowUpRule.R1_FACT_TO_PATTERN: (
        "The answer gives a concrete fact or event. Ask what recurring pattern, "
        "trigger, or repeated experience this points to."
    ),
    FollowUpRule.R2_PATTERN_TO_PRINCIPLE: (
        "The answer describes a pattern or preference. Ask what value, need, "
        "boundary, or tradeoff is underneath it."
    ),
    FollowUpRule.R3_PRINCIPLE_TO_COUNTEREXAMPLE: (
        "The answer states a broad principle. Ask for an exception, limit, "
        "or situation where they would choose differently."
    ),
    FollowUpRule.R4_ABSTRACT_TO_CONCRETE: (
        "The answer is abstract or generalized. Ask for one concrete recent "
        "moment, behavior, or decision that shows it."
    ),
    FollowUpRule.R5_REPEAT_TO_TRIANGULATE: (
        "The answer repeats a known theme. Ask from a new angle: pressure, "
        "cost, contrast, trigger, or what would change it."
    ),
}


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
    if _signals_already_answered(answer):
        return None
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
    if _has_specific_cjk_rationale(answer):
        return None
    return None if _has_concrete_example(answer) else FollowUpRule.R3_PRINCIPLE_TO_COUNTEREXAMPLE


async def generate_follow_up(
    rule: FollowUpRule, answer: str, original_question: str, claude: AsyncAnthropic
) -> str:
    if rule == FollowUpRule.R5_REPEAT_TO_TRIANGULATE:
        return "這個原則我想我們已經談得夠清楚了。讓我換個角度問。"
    rule_instruction = FOLLOW_UP_RULE_PROMPTS[rule]
    prompt = f"""
Generate one short follow-up question.

Rule: {rule.value}
Rule instruction: {rule_instruction}

Original question: {original_question}
Answer: {answer}

Before writing the question, silently identify the answer's most important anchor.
Priority order:
1. explicit strong emotion or distress
2. meaning, self-worth, belonging, or feeling unseen
3. decision pressure, urge, boundary, or action tendency
4. concrete event, relationship, or repeated pattern
5. wording style

Use the user's meaningful content words when helpful.
Do not focus on hedge or filler words such as 「有點」「好像」「可能」「大概」「其實」「就是」 unless the hedge itself is clearly the main point.
Do not ask what a hedge word "means" or what is "behind" a hedge word.
Ask about the substantive or emotional core of the answer.

{INTERVIEW_OUTPUT_LANGUAGE}
Return only one short question.
Do not advise, praise, diagnose, explain, or summarize.
"""
    response = await create_message(
        claude,
        model=MODEL_STANDARD,
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


def _signals_already_answered(answer: str) -> bool:
    normalized = answer.lower()
    markers = (
        "前面說過",
        "剛剛說過",
        "已經講過",
        "已經說過",
        "不是說了",
        "as i said",
        "like i said",
        "already said",
    )
    return any(marker in normalized for marker in markers)


def _has_specific_cjk_rationale(answer: str) -> bool:
    """Avoid asking another "why" when a principle answer already carries a reason.

    This intentionally stays lightweight: no semantic model, just CJK markers
    that indicate the user gave a concrete rationale or behavioral evidence.
    """
    if length_units(answer) < 10:
        return False
    behavior_markers = (
        "會",
        "會不會",
        "一定",
        "每次",
        "通常",
        "主動",
        "持續",
        "花時間",
        "下班",
        "私人時間",
        "任務",
        "工作",
        "專案",
        "交班",
        "回報",
        "追查",
        "時程",
    )
    rationale_markers = (
        "因為",
        "所以",
        "讓我",
        "讓人",
        "代表",
        "表示",
        "認真",
        "放心",
        "確定",
        "穩定",
        "不會",
    )
    return any(marker in answer for marker in behavior_markers) and any(
        marker in answer for marker in rationale_markers
    )
