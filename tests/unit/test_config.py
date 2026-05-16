from virtualme.config import Settings


def test_adaptive_extraction_defaults_are_disabled():
    settings = Settings(anthropic_api_key="test")

    assert settings.adaptive_extraction is False
    assert settings.max_extraction_rounds == 3
