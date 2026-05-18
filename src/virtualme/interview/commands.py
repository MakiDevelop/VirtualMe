"""Lightweight interview command detection — BW7.

Two interactions that are *not* interview answers and must not be extracted:

- status query  -- "which personality block are we collecting right now?"
- re-talk request -- "let's redo the VOICE block"

Detection is keyword-based (CJK + English) and length-capped: a PoC-scale
heuristic, not an LLM intent classifier. A long storytelling answer that
happens to contain a keyword is left alone (see COMMAND_MAX_LEN). Known
limitation: a short genuine answer containing e.g. "重談" can false-trigger.
"""

from __future__ import annotations

from dataclasses import dataclass

from virtualme.storage.db import Dimension
from virtualme.subject import CompletenessReport

# Commands are short. Anything longer is treated as a real interview answer.
COMMAND_MAX_LEN = 40

# Human-facing Chinese labels for each extraction dimension.
DIMENSION_LABELS: dict[Dimension, str] = {
    Dimension.SOUL: "靈魂・核心價值",
    Dimension.VOICE: "語氣・表達",
    Dimension.SKILL: "專業技能",
    Dimension.PEOPLE: "人際關係",
    Dimension.HISTORY: "人生歷程",
    Dimension.JOURNAL: "反思札記",
    Dimension.BOUNDARIES: "界線・原則",
    Dimension.STATE: "近況",
}

# Keywords that point at a specific dimension. First dimension to match wins.
DIMENSION_KEYWORDS: dict[Dimension, list[str]] = {
    Dimension.SOUL: ["soul", "靈魂", "核心價值", "價值觀", "信念"],
    Dimension.VOICE: ["voice", "語氣", "口吻", "表達", "說話方式"],
    Dimension.SKILL: ["skill", "技能", "專業", "能力"],
    Dimension.PEOPLE: ["people", "人際", "人脈", "同事", "夥伴", "關係"],
    Dimension.HISTORY: ["history", "歷程", "經歷", "過去"],
    Dimension.JOURNAL: ["journal", "札記", "反思", "日誌"],
    Dimension.BOUNDARIES: ["boundaries", "界線", "界限", "原則", "底線", "紅線"],
    Dimension.STATE: ["state", "近況", "現況"],
}

STATUS_KEYWORDS = [
    "現在在問",
    "在問什麼",
    "在收集",
    "收集哪",
    "收集到哪",
    "哪一塊",
    "哪一個維度",
    "目前進度",
    "目前訪談",
    "訪談進度",
    "訪談的進度",
    "進度如何",
    "萃取進度",
    "完成度",
    "有哪些主題",
    "八大主題",
    "訪談範圍",
    "萃取範圍",
    "人格主題",
    "人格維度",
    "針對哪",
    "到哪了",
    "which block",
    "which dimension",
    "what are we",
    "progress",
]

RETALK_KEYWORDS = [
    "重談",
    "重新談",
    "再談一次",
    "重新講",
    "重新訪談",
    "重來",
    "redo",
    "re-talk",
    "retalk",
]

RESTART_KEYWORDS = [
    "重頭開始",
    "從頭開始",
    "重新開始萃取",
    "重頭開始萃取",
    "全部重來",
    "全部重新",
    "整個訪談重來",
    "整個萃取重來",
    "restart interview",
    "restart extraction",
    "start over",
]


@dataclass
class StatusQuery:
    """User asked which dimension is being collected."""


@dataclass
class RetalkRequest:
    """User asked to re-interview a dimension. ``dimension`` is None when the
    request did not name a recognisable block."""

    dimension: Dimension | None


@dataclass
class RestartRequest:
    """User asked to restart the whole extraction run."""


@dataclass
class GenerateProfileRequest:
    """User asked to export the current snapshot/persona draft."""


InterviewCommand = StatusQuery | RetalkRequest | RestartRequest | GenerateProfileRequest


GENERATE_PROFILE_KEYWORDS = [
    "產生人格檔",
    "生成人格檔",
    "匯出人格檔",
    "輸出人格檔",
    "產出人格檔",
    "建立人格檔",
    "產生 persona",
    "生成 persona",
    "export persona",
    "generate profile",
    "export profile",
]


def _match_dimension(text: str) -> Dimension | None:
    for dimension, keywords in DIMENSION_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return dimension
    return None


def detect_command(message: str) -> InterviewCommand | None:
    """Return an InterviewCommand if the message is a meta-command, else None."""
    stripped = message.strip()
    if not stripped or len(stripped) > COMMAND_MAX_LEN:
        return None
    text = stripped.lower()
    if any(keyword in text for keyword in RESTART_KEYWORDS):
        return RestartRequest()
    if any(keyword in text for keyword in GENERATE_PROFILE_KEYWORDS):
        return GenerateProfileRequest()
    if any(keyword in text for keyword in RETALK_KEYWORDS):
        return RetalkRequest(dimension=_match_dimension(text))
    if any(keyword in text for keyword in STATUS_KEYWORDS):
        return StatusQuery()
    return None


def format_status_reply(
    current_dimension: Dimension,
    covered_dimensions: list[Dimension],
    completeness: CompletenessReport | None = None,
) -> str:
    current = DIMENSION_LABELS[current_dimension]
    if covered_dimensions:
        covered = "、".join(DIMENSION_LABELS[dim] for dim in covered_dimensions)
        covered_line = f"目前已經收集到的維度：{covered}。"  # noqa: RUF001
    else:
        covered_line = "目前還沒有任何維度收集到內容。"
    lines = [
        f"我們現在正在收集的人格維度是【{current}】。\n"
        f"{covered_line}",
        "",
        "八大萃取主題:",
    ]
    if completeness is None:
        for dimension in Dimension:
            marker = " ← 目前" if dimension == current_dimension else ""
            lines.append(f"- {DIMENSION_LABELS[dimension]}{marker}")
    else:
        by_dimension = {score.dimension: score for score in completeness.per_dimension}
        for dimension in Dimension:
            score = by_dimension[dimension]
            marker = " ← 目前" if dimension == current_dimension else ""
            lines.append(
                f"- {DIMENSION_LABELS[dimension]}: {score.coverage:.0%} "
                f"({score.anchor_count} anchors, {score.triangulated_count} confirmed){marker}"
            )
        lines.extend(
            [
                "",
                f"總完成度: {completeness.total_score:.1f}%",
            ]
        )
        if completeness.weakest is not None:
            lines.append(f"目前最缺: {DIMENSION_LABELS[completeness.weakest]}")
    lines.extend(
        [
            "",
            "如果想重談某一塊，可以跟我說「重談 + 維度名稱」（例如「重談 人際關係」）。",  # noqa: RUF001
        ]
    )
    return "\n".join(lines)


def format_retalk_reply(dimension: Dimension, question_text: str) -> str:
    label = DIMENSION_LABELS[dimension]
    return f"好，我們重新談【{label}】這一塊。\n{question_text}"  # noqa: RUF001


def format_retalk_needs_dimension() -> str:
    blocks = "、".join(DIMENSION_LABELS.values())
    return (
        "你想重談哪一塊呢？可選的人格維度有：\n"  # noqa: RUF001
        f"{blocks}。\n"
        "跟我說「重談 + 維度名稱」就可以了。"
    )


def format_restart_reply(archive_note: str, archived_counts: dict[str, int], first_question: str) -> str:
    return (
        "好, 我會從頭開始萃取。\n"
        f"{archive_note}\n"
        "舊資料已封存, 不會刪除; 新的萃取會從 0 開始累積。\n"
        f"封存摘要: anchors {archived_counts['anchors']}, "
        f"triples {archived_counts['triples']}, sessions {archived_counts['sessions']}。\n"
        f"{first_question}"
    )


def format_generate_profile_reply(file_names: list[str]) -> str:
    files = "、".join(file_names)
    return (
        "已產生目前的人格檔草稿。\n"
        "這是 pre-alpha snapshot, 不是定稿; 請先由 Maki / operator review 後再使用。\n"
        f"已輸出檔案: {files}"
    )
