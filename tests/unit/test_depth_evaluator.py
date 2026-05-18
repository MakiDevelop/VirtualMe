import json

from virtualme.interview.depth_evaluator import TurnKind, evaluate_depth
from virtualme.storage.db import Layer


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self, text: str):
        self.text = text

    async def create(self, **kwargs):
        return type("Response", (), {"content": [_Content(self.text)]})


class _Claude:
    def __init__(self, text: str):
        self.messages = _Messages(text)


def _assessment(
    kind: str = "SUFFICIENT",
    depth: str = "principle",
    follow_up: bool = False,
    confidence: float = 0.9,
) -> str:
    return json.dumps(
        {
            "kind": kind,
            "depth": depth,
            "needs_follow_up": follow_up,
            "confidence": confidence,
        }
    )


async def test_depth_fact():
    assessment = await evaluate_depth(
        "I yelled at my manager once", "What happened?", _Claude(_assessment(depth="fact"))
    )
    assert assessment.depth == Layer.FACT
    assert assessment.kind == TurnKind.SUFFICIENT


async def test_depth_pattern():
    answer = "I always speak my mind regardless of authority"
    assessment = await evaluate_depth(
        answer, "How do you handle authority?", _Claude(_assessment(depth="pattern"))
    )
    assert assessment.depth == Layer.PATTERN


async def test_depth_principle():
    answer = "I value directness because trust requires people to know where they stand"
    assessment = await evaluate_depth(
        answer, "What do you value?", _Claude(_assessment(depth="principle"))
    )
    assert assessment.depth == Layer.PRINCIPLE


async def test_depth_parse_failure_is_conservative():
    assessment = await evaluate_depth("answer", "Question?", _Claude("not json"))
    assert assessment.kind == TurnKind.SUFFICIENT
    assert assessment.depth == Layer.FACT
    assert assessment.needs_follow_up is False
    assert assessment.parse_failed is True


async def test_depth_accepts_markdown_fenced_json():
    assessment = await evaluate_depth(
        "I value directness.",
        "What do you value?",
        _Claude(f"```json\n{_assessment(depth='principle')}\n```"),
    )
    assert assessment.kind == TurnKind.SUFFICIENT
    assert assessment.depth == Layer.PRINCIPLE
    assert assessment.parse_failed is False


async def test_low_confidence_evasion_downgrades_to_thin_follow_up():
    assessment = await evaluate_depth(
        "我有點迷惑, 有時我會覺得我的工作有價值嗎?",
        "請說說您最近的工作狀況。",
        _Claude(_assessment(kind="EVASION", confidence=0.5)),
    )

    assert assessment.kind == TurnKind.THIN
    assert assessment.needs_follow_up is True


async def test_high_confidence_evasion_stays_evasion():
    assessment = await evaluate_depth(
        "跳過這題, 我想換一個。",
        "請說說您最近的工作狀況。",
        _Claude(_assessment(kind="EVASION", confidence=0.9)),
    )

    assert assessment.kind == TurnKind.EVASION
    assert assessment.needs_follow_up is False
