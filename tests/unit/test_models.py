from virtualme.interview.models import MODEL_DEEP, MODEL_FAST, MODEL_STANDARD


def test_model_tiers_use_expected_defaults():
    assert MODEL_FAST == "claude-haiku-4-5"
    assert MODEL_STANDARD == "claude-sonnet-4-6"
    assert MODEL_DEEP == "claude-opus-4-7"
