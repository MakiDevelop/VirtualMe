"""Deterministic liability-topic detection for the HR/HRBP responder.

HR replies that touch labour law, compensation, harassment, discrimination,
or personal data carry legal weight. These topics get a "confirm with the
real person" nudge and are forwarded to the owner. Detection is a simple,
transparent substring match: no LLM, no network.
"""

LIABILITY_MARKERS = frozenset(
    {
        "勞基法",
        "勞動基準法",
        "勞動法",
        "資遣",
        "資遣費",
        "解僱",
        "解雇",
        "開除",
        "加班費",
        "薪資",
        "調薪",
        "減薪",
        "性騷",
        "性騷擾",
        "歧視",
        "申訴",
        "檢舉",
        "個資",
        "個人資料",
        "育嬰",
        "產假",
        "陪產假",
        "試用期",
        "競業",
        "競業條款",
        "勞檢",
        "訴訟",
        "法律責任",
        "違法",
        "職災",
        "退休金",
        "勞保",
    }
)


def is_liability_topic(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in LIABILITY_MARKERS)
