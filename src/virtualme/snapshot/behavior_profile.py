from __future__ import annotations

from typing import Final

from virtualme.snapshot.core import SnapshotBundle, _strip_hypothesis_prefix
from virtualme.storage.db import Dimension

_CONSTRUCT_FAMILY_NARRATIVES: Final = {
    "Constraint triangle integrity": {
        "topic": "事情兜不攏的時候",
        "context": "一件事同時要求固定的成果、固定的資源、固定的時間，而這三者其實無法兼顧時",
        "tendency": "會把衝突直接攤開，要求其中一邊讓步，而不是假裝原案還能照走",
        "value": "交付到最後能不能真的做得到",
    },
    "Invalid-condition confrontation": {
        "topic": "一個前提本身就不成立的時候",
        "context": "一件事的基本前提其實站不住腳，但繼續順著講、場面會比較好看時",
        "tendency": "會先把那個不成立的地方講出來，再回頭處理關係和語氣",
        "value": "誠實地把問題看清楚",
    },
    "Handoff as commitment signal": {
        "topic": "別人把事情交到你手上之前",
        "context": "一件事要從別人手上交接過來，對方只說「做完了」，卻沒留下足夠的脈絡時",
        "tendency": (
            "會先看交接交得夠不夠清楚，再決定能不能接著順下去——比起評斷一個人，"
            "更像在確認事情本身接不接得起來"
        ),
        "value": "事情能不能接著順利運作",
    },
    "Emotional-pressure pricing boundary": {
        "topic": "商量被包裝成「交情」的時候",
        "context": "一場商量被說成「你幫我就是夠朋友、夠在乎」，不讓步好像就是不近人情時",
        "tendency": "會把交情和實際條件分開談，回到價值、成本、還有有沒有別的選項",
        "value": "交換是不是公平",
    },
    "Action over attribution": {
        "topic": "可能被傷害、但對方動機不明的時候",
        "context": "你可能被某個人傷害或拖累，但對方到底是不是故意的、還看不清楚時",
        "tendency": (
            "會先針對「已經看得到的影響」採取行動，而不是把力氣花在證明對方在想什麼"
        ),
        "value": "自己實際的主導權",
    },
}

_DIMENSION_LABELS: Final = {
    Dimension.SOUL: "核心價值",
    Dimension.BOUNDARIES: "界線",
    Dimension.VOICE: "表達方式",
    Dimension.SKILL: "做事方式",
    Dimension.PEOPLE: "人際",
    Dimension.HISTORY: "經歷",
    Dimension.JOURNAL: "反思",
    Dimension.STATE: "當前狀態",
}

_CHINESE_NUMERALS: Final = ("一", "二", "三", "四", "五")

_OBSERVATION_NOTE: Final = (
    "這是一次談話留下的初步觀察，需要你自己確認才算數。"
    "如果不太像你，你心裡浮現的那個反例，會比這份檔案更接近真相。"
)


def render_behavior_profile(bundle: SnapshotBundle) -> str:
    date = bundle.generated_at.partition("T")[0] or bundle.generated_at
    lines = [
        "# 行為模式檔 v0",
        "",
        "> 這是一份初步觀察草稿，整理自你的一次訪談。",
        "> 它不是心理診斷，也不是定論——它描述的是「在那次談話裡，你怎麼說自己」。",
        "> 看到不準的地方很正常。",
        "",
        f"觀察於 {date}。這是一份快照——建議你看過一次後，過幾週就把它放下或丟掉。它描述的是過去，不是對未來的承諾。",
        "",
        "## 在訪談裡浮現的幾種傾向",
        "",
    ]

    if bundle.construct_cards:
        lines.extend(_construct_card_sections(bundle))
    elif bundle.hypotheses:
        lines.extend(_hypothesis_sections(bundle))
    else:
        lines.append("_目前的訪談資料還不足以整理出可談的行為模式。這不是壞事——它只表示你還沒聊夠。建議再進行幾輪訪談後重新產生。_")
        lines.append("")

    lines.extend(
        [
            "## 這份檔案最可能不準的地方",
            "",
            "它只根據一次訪談整理，沒有長期的佐證。它寫下的是「你怎麼描述自己」，不一定是「你實際會怎麼做」——這兩者常常有差距，而這份檔案看不見那個差距。把上面每一點都當成一個問句，不是一個答案。",
            "",
            "## 讀完之後",
            "",
            "如果這份檔案裡有任何一句讓你覺得「被看見了」——那個感覺是真的，也值得珍惜。但它屬於一個人，不屬於這份檔案。",
            "",
            "最好的下一步，不是再產一份檔案，是把這裡面任何一點，帶去跟一個了解你的人聊：「這像我嗎？」他們的回答，會比這份草稿準得多。",
        ]
    )
    return "\n".join(lines)


def _construct_card_sections(bundle: SnapshotBundle) -> list[str]:
    lines: list[str] = []
    for index, card in enumerate(bundle.construct_cards[:5]):
        narrative = _CONSTRUCT_FAMILY_NARRATIVES.get(card.title)
        numeral = _CHINESE_NUMERALS[index]
        topic = narrative["topic"] if narrative else card.title
        lines.append(f"### {numeral}、關於「{topic}」")
        lines.append("")
        if narrative is None:
            lines.append(f"（這個型樣還沒有對應的中文描述。系統記錄的原始描述是：{card.trigger_context}）")
        else:
            lines.append(
                f"當{narrative['context']}——在那次訪談裡，你描述自己"
                f"{narrative['tendency']}。你說你在意的，是{narrative['value']}。"
            )
        lines.append("")
        lines.append(_OBSERVATION_NOTE)
        lines.append("")
    return lines


def _hypothesis_sections(bundle: SnapshotBundle) -> list[str]:
    lines: list[str] = []
    for index, hypothesis in enumerate(bundle.hypotheses[:5]):
        numeral = _CHINESE_NUMERALS[index]
        label = _DIMENSION_LABELS.get(hypothesis.dimension, hypothesis.dimension.value)
        evidence = _strip_hypothesis_prefix(hypothesis.hypothesis)
        lines.append(f"### {numeral}、關於你在訪談裡提到的一件事")
        lines.append("")
        lines.append(f"在那次訪談裡，你描述自己{evidence}（這屬於你的{label}）。")
        lines.append("")
        lines.append(_OBSERVATION_NOTE)
        lines.append("")
    return lines
