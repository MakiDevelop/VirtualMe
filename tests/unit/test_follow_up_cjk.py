from virtualme.interview.follow_up import (
    FollowUpRule,
    _has_concrete_example,
    _has_specific_cjk_rationale,
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
