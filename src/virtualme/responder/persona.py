"""Load an exported VirtualMe persona archive into a prompt context string."""

from __future__ import annotations

from pathlib import Path

PERSONA_FILES = ["SOUL.md", "VOICE.md", "BOUNDARIES.md", "SKILL.md", "PEOPLE.md"]


def load_persona(persona_dir: str | Path) -> str:
    """Read key persona markdown files from an export folder."""
    directory = Path(persona_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"persona dir not found: {directory}")

    sections: list[str] = []
    for name in PERSONA_FILES:
        path = directory / name
        if path.is_file():
            sections.append(f"=== {name} ===\n{path.read_text(encoding='utf-8').strip()}")
    return "\n\n".join(sections)
