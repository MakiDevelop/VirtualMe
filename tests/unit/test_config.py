from virtualme.config import Settings


def test_adaptive_extraction_defaults_are_disabled():
    settings = Settings(anthropic_api_key="test")

    assert settings.adaptive_extraction is False
    assert settings.max_extraction_rounds == 3


def test_reasoner_model_name_accepts_env_alias(monkeypatch):
    monkeypatch.setenv("REASONER_MODEL_NAME", "claude-haiku-4-5")

    settings = Settings(anthropic_api_key="test")

    assert settings.reasoner_model_name == "claude-haiku-4-5"


def test_reasoner_prompt_file_accepts_env_alias(monkeypatch):
    monkeypatch.setenv("REASONER_PROMPT_FILE", ".private/reasoner-system-prompt.txt")

    settings = Settings(anthropic_api_key="test")

    assert settings.reasoner_prompt_file == ".private/reasoner-system-prompt.txt"
