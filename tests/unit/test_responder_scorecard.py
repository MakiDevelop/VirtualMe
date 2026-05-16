from importlib.resources import files

import yaml

from virtualme.config import Settings
from virtualme.responder.liability import is_liability_topic
from virtualme.responder.scorecard import build_scorecard


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self, texts: list[str]):
        self.texts = texts
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"content": [_Content(self.texts.pop(0))]})


class _Claude:
    def __init__(self, texts: list[str]):
        self.messages = _Messages(texts)


def _settings() -> Settings:
    return Settings(anthropic_api_key="test")


def test_poc_messages_yaml_loads_expected_messages():
    text = files("virtualme.responder").joinpath("poc_messages.yaml").read_text("utf-8")
    data = yaml.safe_load(text)

    messages = data["messages"]
    liability_count = sum(is_liability_topic(message["text"]) for message in messages)

    assert len(messages) == 12
    assert all(message["id"] and message["text"] for message in messages)
    assert 3 <= liability_count <= 5


async def test_build_scorecard_renders_messages_replies_and_manual_fields(tmp_path):
    (tmp_path / "SOUL.md").write_text("務實、溫和、直接", encoding="utf-8")
    replies = [f"mock reply {index:02d}" for index in range(1, 13)]
    claude = _Claude(replies.copy())

    markdown = await build_scorecard(tmp_path, claude, _settings())

    assert "# VirtualMe HR PoC Responder Scorecard" in markdown
    assert f"Persona dir: {tmp_path}" in markdown
    assert len(claude.messages.calls) == 12
    for index in range(1, 13):
        assert f"### M{index:02d}" in markdown
        assert f"mock reply {index:02d}" in markdown
    assert "voice 像我嗎 (1-5)" in markdown
    assert "correctness 專業對嗎 (1-5)" in markdown
    assert "acceptability 這樣回出去OK嗎 (Y/N)" in markdown
    assert "備註" in markdown
    assert "voice+acceptability ≥8/12 可送出" in markdown
