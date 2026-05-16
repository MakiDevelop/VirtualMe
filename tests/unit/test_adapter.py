import pytest

from virtualme.persona.adapter import load_persona_for_runtime, to_provider_payload


def _write_dimension(persona_dir, dimension: str, content: str) -> None:
    (persona_dir / f"{dimension}.md").write_text(content, encoding="utf-8")


def test_load_persona_uses_fixed_start_here_order(tmp_path):
    for dimension in ["STATE", "SOUL", "SKILL", "VOICE", "BOUNDARIES"]:
        _write_dimension(tmp_path, dimension, f"{dimension.lower()} body")

    text = load_persona_for_runtime(tmp_path, "openclaw")

    headings = [
        line for line in text.splitlines() if line.startswith("=== ") and line.endswith(" ===")
    ]
    assert headings == [
        "=== SOUL ===",
        "=== VOICE ===",
        "=== BOUNDARIES ===",
        "=== SKILL ===",
        "=== STATE ===",
    ]


def test_load_persona_skips_missing_dimension_files(tmp_path):
    _write_dimension(tmp_path, "SOUL", "core")
    _write_dimension(tmp_path, "STATE", "now")

    text = load_persona_for_runtime(tmp_path, "openclaw")

    assert "=== SOUL ===" in text
    assert "=== STATE ===" in text
    assert "=== VOICE ===" not in text


def test_load_persona_truncates_with_marker(tmp_path):
    _write_dimension(tmp_path, "SOUL", "x" * 100)

    text = load_persona_for_runtime(tmp_path, "openai", char_limit=40)

    assert len(text) == 40
    assert text.endswith("[truncated]")


def test_to_provider_payload_system_shapes():
    assert to_provider_payload("persona", "claude") == {"system": "persona"}
    assert to_provider_payload("persona", "openclaw") == {"system": "persona"}
    assert to_provider_payload("persona", "grok") == {"system": "persona"}
    assert to_provider_payload("persona", "openai") == {
        "messages": [{"role": "system", "content": "persona"}]
    }
    assert to_provider_payload("persona", "gemini") == {"system_instruction": "persona"}


def test_to_provider_payload_rejects_unknown_runtime():
    with pytest.raises(ValueError):
        to_provider_payload("persona", "unknown")
