from virtualme.interview.briefing import INTERVIEW_PURPOSE, InterviewBriefing
from virtualme.interview.follow_up import (
    FOLLOW_UP_RULE_PROMPTS,
    FollowUpRule,
    _has_concrete_example,
    _has_specific_cjk_rationale,
    generate_follow_up,
    select_rule,
)
from virtualme.storage.db import Layer


def test_select_rule_returns_r4_for_short_cjk_abstract_answer():
    assert select_rule("我覺得誠實信任最重要", Layer.PRINCIPLE, []) == FollowUpRule.R4_ABSTRACT_TO_CONCRETE


def test_has_concrete_example_detects_cjk_marker():
    assert _has_concrete_example("有一次我跟客戶討論需求時很直接") is True


def test_select_rule_stops_when_user_says_already_answered():
    assert select_rule("前面說過了 他會花私人時間持續研究", Layer.PRINCIPLE, []) is None


def test_select_rule_does_not_probe_specific_cjk_rationale_again():
    answer = "他接下來的任務一定會認真對待"

    assert _has_specific_cjk_rationale(answer) is True
    assert select_rule(answer, Layer.PRINCIPLE, []) is None


def test_follow_up_rule_prompts_cover_all_rules():
    assert set(FOLLOW_UP_RULE_PROMPTS) == set(FollowUpRule)


async def test_generate_follow_up_prompt_includes_rule_instruction_and_anchor_guidance(monkeypatch):
    captured = {}

    class FakeContent:
        def __init__(self, text):
            self.text = text

    class FakeResponse:
        def __init__(self, text):
            self.content = [FakeContent(text)]

    async def fake_create_message(*args, **kwargs):
        captured["messages"] = kwargs["messages"]
        return FakeResponse("你最在意的是哪個部分?")

    monkeypatch.setattr("virtualme.interview.follow_up.create_message", fake_create_message)

    question = "你最近工作狀態怎麼樣?"
    answer = "我覺得我的付出好像可有可無 有點不太想做了"

    result = await generate_follow_up(
        FollowUpRule.R2_PATTERN_TO_PRINCIPLE,
        answer,
        question,
        claude=None,
    )

    prompt = captured["messages"][0]["content"]
    assert result == "你最在意的是哪個部分?"
    assert "Ask what value, need, boundary, or tradeoff is underneath it." in prompt
    assert "Do not ask what a hedge word" in prompt
    assert question in prompt
    assert answer in prompt


async def test_generate_follow_up_prompt_includes_briefing_when_present(monkeypatch):
    captured = {}

    class FakeContent:
        def __init__(self, text):
            self.text = text

    class FakeResponse:
        def __init__(self, text):
            self.content = [FakeContent(text)]

    async def fake_create_message(*args, **kwargs):
        captured["messages"] = kwargs["messages"]
        return FakeResponse("哪個壓力最明顯?")

    monkeypatch.setattr("virtualme.interview.follow_up.create_message", fake_create_message)
    briefing = InterviewBriefing(
        purpose=INTERVIEW_PURPOSE,
        progress="Week 1 of 3.",
        durable_summary="- durable",
        coverage_gaps="- gap",
        recent_transcript="受訪者: 前一輪回答",
    )

    await generate_follow_up(
        FollowUpRule.R1_FACT_TO_PATTERN,
        "我昨天卡住了",
        "最近工作如何?",
        claude=None,
        briefing=briefing,
    )

    prompt = captured["messages"][0]["content"]
    assert "INTERVIEW PURPOSE:" in prompt
    assert "STILL TO COVER:" in prompt
    assert "RECENT CONVERSATION:" in prompt


async def test_generate_follow_up_r5_returns_canned_response_without_llm(monkeypatch):
    async def fake_create_message(*args, **kwargs):
        raise AssertionError("R5 should not call create_message")

    monkeypatch.setattr("virtualme.interview.follow_up.create_message", fake_create_message)

    result = await generate_follow_up(
        FollowUpRule.R5_REPEAT_TO_TRIANGULATE,
        answer="我一直都很重視誠實",
        original_question="你重視什麼?",
        claude=None,
    )

    assert result == "這個原則我想我們已經談得夠清楚了。讓我換個角度問。"
