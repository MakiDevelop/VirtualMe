from __future__ import annotations

from pathlib import Path

DIMENSION_ORDER = (
    "SOUL",
    "VOICE",
    "BOUNDARIES",
    "SKILL",
    "PEOPLE",
    "HISTORY",
    "JOURNAL",
    "STATE",
)

RUNTIME_CHAR_LIMITS: dict[str, int | None] = {
    "openclaw": None,
    "claude": 180_000,
    "openai": 120_000,
    "gemini": 120_000,
    "grok": 120_000,
}


def load_persona_for_runtime(
    persona_dir: str | Path,
    runtime: str,
    char_limit: int | None = None,
) -> str:
    """Load dimension markdowns into a single runtime prompt."""
    directory = Path(persona_dir)
    sections: list[str] = []
    for dimension in DIMENSION_ORDER:
        path = directory / f"{dimension}.md"
        if path.is_file():
            content = path.read_text(encoding="utf-8").strip()
            sections.append(f"=== {dimension} ===\n{content}")

    text = "\n\n".join(sections)
    limit = RUNTIME_CHAR_LIMITS.get(runtime.lower()) if char_limit is None else char_limit
    return _truncate(text, limit)


def to_provider_payload(persona_text: str, runtime: str) -> dict:
    """Map persona text into the provider's system-prompt shape."""
    normalized = runtime.lower()
    if normalized in {"claude", "openclaw", "grok"}:
        return {"system": persona_text}
    if normalized == "openai":
        return {"messages": [{"role": "system", "content": persona_text}]}
    if normalized == "gemini":
        return {"system_instruction": persona_text}
    raise ValueError(f"Unsupported persona runtime: {runtime}")


def _truncate(text: str, limit: int | None) -> str:
    if limit is None or len(text) <= limit:
        return text
    marker = "\n[truncated]"
    if limit <= len(marker):
        return marker[:limit]
    return f"{text[: limit - len(marker)]}{marker}"
