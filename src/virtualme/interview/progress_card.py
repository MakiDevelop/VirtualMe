"""
Progress Card Renderer for LINE Flex Message

Generates a visual 8-dimension × 3-layer progress card.
This is designed for L3, but the data shape is compatible with what L2 TurnReasoner will eventually receive.

Usage:
    snapshot = {
        "VOICE": {"shallow": 0.9, "middle": 0.4, "deep": 0.0},
        ...
    }
    flex_message = build_progress_flex(snapshot, trigger="user_asked")
"""


DIMENSION_LABELS = {
    "VOICE": "聲音 / 表達",
    "BOUNDARIES": "界線 / 責任",
    "SOUL": "靈魂 / 價值觀",
    "SKILL": "專業技能",
    "PEOPLE": "人際關係",
    "HISTORY": "經歷 / 歷史",
    "JOURNAL": "日誌 / 日常",
    "STATE": "當下狀態 / 能量",
}

LAYER_ORDER = ["shallow", "middle", "deep"]
LAYER_LABELS = {
    "shallow": "淺層",
    "middle": "中層",
    "deep": "深層",
}

# Color scheme (LINE friendly)
COLORS = {
    "shallow": "#A5D6A7",   # Light green
    "middle": "#66BB6A",    # Medium green
    "deep": "#2E7D32",      # Dark green
    "none": "#E0E0E0",
    "header": "#1A237E",
    "text": "#212121",
}


def _layer_segment(status: str, layer: str, width: int = 3) -> dict:
    """Create one small colored box representing a layer segment."""
    color = COLORS.get(status, COLORS["none"])
    return {
        "type": "box",
        "layout": "vertical",
        "width": f"{width}px",
        "height": "18px",
        "backgroundColor": color,
        "cornerRadius": "4px",
    }


def _build_dimension_row(dim_key: str, progress: dict) -> dict:
    """Build one row for a dimension with 3 layer segments."""
    label = DIMENSION_LABELS.get(dim_key, dim_key)

    segments = []
    for layer in LAYER_ORDER:
        score = progress.get(layer, 0.0)
        if score >= 0.8:
            status = layer  # use the layer color
        elif score >= 0.4:
            status = layer
        else:
            status = "none"
        segments.append(_layer_segment(status, layer))

    # Simple text summary
    reached = "尚未開始"
    if progress.get("deep", 0) > 0.5:
        reached = "已跨深層"
    elif progress.get("middle", 0) > 0.5:
        reached = "已跨中層"
    elif progress.get("shallow", 0) > 0.5:
        reached = "已跨淺層"

    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "sm",
        "contents": [
            {
                "type": "text",
                "text": label,
                "size": "sm",
                "color": COLORS["text"],
                "flex": 3,
            },
            {
                "type": "box",
                "layout": "horizontal",
                "spacing": "2px",
                "contents": segments,
                "flex": 4,
            },
            {
                "type": "text",
                "text": reached,
                "size": "xs",
                "color": "#616161",
                "flex": 3,
                "align": "end",
            },
        ],
    }


def build_progress_flex(
    snapshot: dict[str, dict],
    trigger: str = "user_asked",
) -> dict:
    """
    Generate LINE Flex Message (bubble) for interview progress.

    snapshot example:
    {
        "SKILL": {"shallow": 0.95, "middle": 0.65, "deep": 0.1},
        "VOICE": {"shallow": 0.8, "middle": 0.3, "deep": 0.0},
        ...
    }
    """
    contents = []

    # Header
    contents.append({
        "type": "text",
        "text": "目前訪談收集進度",
        "weight": "bold",
        "size": "xl",
        "color": COLORS["header"],
    })

    contents.append({
        "type": "text",
        "text": "八維 × 三層（淺層 → 中層 → 深層）",
        "size": "xs",
        "color": "#757575",
        "margin": "sm",
    })

    # Separator
    contents.append({"type": "separator", "margin": "md"})

    # Dimension rows
    for dim in ["VOICE", "BOUNDARIES", "SOUL", "SKILL", "PEOPLE", "HISTORY", "JOURNAL", "STATE"]:
        prog = snapshot.get(dim, {"shallow": 0, "middle": 0, "deep": 0})
        contents.append(_build_dimension_row(dim, prog))

    # Footer note
    contents.append({"type": "separator", "margin": "lg"})
    contents.append({
        "type": "text",
        "text": "只有當回答貢獻有意義的證據時才會推進進度。\n想繼續哪一塊？可以直接告訴我。",
        "size": "xs",
        "color": "#616161",
        "wrap": True,
    })

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "VirtualMe 訪談進度",
                    "size": "sm",
                    "color": "#FFFFFF",
                    "weight": "bold",
                }
            ],
            "backgroundColor": COLORS["header"],
            "paddingAll": "12px",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": contents,
        },
    }

    return {
        "type": "flex",
        "altText": "目前訪談收集進度",
        "contents": bubble,
    }


# Convenience function for bot.py integration
def get_progress_flex_for_user(
    interviewee_id: str,
    trigger: str = "user_asked",
) -> dict:
    """
    Returns the full Flex Message payload ready to be sent.
    For now uses a realistic sample snapshot (will be replaced by real CoverageSnapshot later).
    """
    # Realistic snapshot based on recent dogfood session (SKILL has the most progress)
    snapshot = {
        "VOICE": {"shallow": 0.6, "middle": 0.25, "deep": 0.0},
        "BOUNDARIES": {"shallow": 0.35, "middle": 0.05, "deep": 0.0},
        "SOUL": {"shallow": 0.45, "middle": 0.15, "deep": 0.0},
        "SKILL": {"shallow": 0.92, "middle": 0.68, "deep": 0.12},  # strongest
        "PEOPLE": {"shallow": 0.55, "middle": 0.28, "deep": 0.0},
        "HISTORY": {"shallow": 0.78, "middle": 0.35, "deep": 0.0},
        "JOURNAL": {"shallow": 0.22, "middle": 0.0, "deep": 0.0},
        "STATE": {"shallow": 0.65, "middle": 0.18, "deep": 0.0},
    }
    return build_progress_flex(snapshot, trigger=trigger)
