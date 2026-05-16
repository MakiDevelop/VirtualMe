import pytest

from virtualme.config import Settings
from virtualme.responder.core import DISCLOSURE_FOOTER, LIABILITY_NUDGE, respond
from virtualme.responder.liability import is_liability_topic
from virtualme.responder.persona import load_persona


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


def test_load_persona_concatenates_existing_files_and_skips_missing(tmp_path):
    (tmp_path / "SOUL.md").write_text("核心價值", encoding="utf-8")
    (tmp_path / "VOICE.md").write_text("溫和直接", encoding="utf-8")

    context = load_persona(tmp_path)

    assert "=== SOUL.md ===\n核心價值" in context
    assert "=== VOICE.md ===\n溫和直接" in context
    assert "BOUNDARIES.md" not in context


def test_load_persona_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_persona(tmp_path / "missing")


@pytest.mark.parametrize("text", ["資遣怎麼談", "遇到性騷擾怎麼處理", "勞基法怎麼看"])
def test_is_liability_topic_returns_true_for_liability_markers(text):
    assert is_liability_topic(text) is True


def test_is_liability_topic_returns_false_for_general_question():
    assert is_liability_topic("請問貴公司福利") is False


async def test_respond_adds_disclosure_for_general_message():
    claude = _Claude(["可以, 我會用比較務實的角度回答。"])

    result = await respond("請問貴公司福利", "persona context", claude, _settings())

    assert result.reply.endswith(DISCLOSURE_FOOTER)
    assert LIABILITY_NUDGE not in result.reply
    assert result.is_liability is False


async def test_respond_adds_liability_nudge_and_disclosure_for_liability_message():
    claude = _Claude(["資遣費通常要先確認年資與平均工資。"])

    result = await respond("想問資遣費怎麼算", "persona context", claude, _settings())

    assert LIABILITY_NUDGE in result.reply
    assert result.reply.endswith(DISCLOSURE_FOOTER)
    assert result.is_liability is True
