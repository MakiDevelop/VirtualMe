from virtualme.interview.follow_up import (
    FollowUpRule,
    _has_concrete_example,
    select_rule,
)
from virtualme.storage.db import Layer


def test_select_rule_returns_r4_for_short_cjk_abstract_answer():
    assert select_rule("我覺得誠實信任最重要", Layer.PRINCIPLE, []) == FollowUpRule.R4_ABSTRACT_TO_CONCRETE


def test_has_concrete_example_detects_cjk_marker():
    assert _has_concrete_example("有一次我跟客戶討論需求時很直接") is True
