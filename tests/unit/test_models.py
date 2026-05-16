from virtualme.interview.models import MODEL_DEEP, MODEL_FAST, MODEL_STANDARD, create_message


def test_model_tiers_use_expected_defaults():
    assert MODEL_FAST == "claude-haiku-4-5"
    assert MODEL_STANDARD == "claude-sonnet-4-6"
    assert MODEL_DEEP == "claude-opus-4-7"


class _Messages:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return "ok"


class _Claude:
    def __init__(self):
        self.messages = _Messages()


async def test_create_message_strips_temperature_for_unsupported_model():
    claude = _Claude()
    response = await create_message(
        claude,
        model=MODEL_DEEP,
        max_tokens=1,
        temperature=0.3,
        messages=[{"role": "user", "content": "ping"}],
    )
    assert response == "ok"
    assert claude.messages.kwargs == {
        "model": MODEL_DEEP,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ping"}],
    }


async def test_create_message_preserves_temperature_for_supported_model():
    claude = _Claude()
    await create_message(
        claude,
        model=MODEL_STANDARD,
        max_tokens=1,
        temperature=0.3,
        messages=[{"role": "user", "content": "ping"}],
    )
    assert claude.messages.kwargs["temperature"] == 0.3
