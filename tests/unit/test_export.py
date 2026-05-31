import hashlib
import json

import aiosqlite
from pydantic import ValidationError

from virtualme.export.__main__ import main
from virtualme.export.markdown import export_markdown
from virtualme.storage.db import DB, Dimension, Layer

ARCHIVE_FILES = {
    "START_HERE.md",
    "index.md",
    "manifest.json",
    "SOUL.md",
    "VOICE.md",
    "SKILL.md",
    "PEOPLE.md",
    "HISTORY.md",
    "JOURNAL.md",
    "BOUNDARIES.md",
    "STATE.md",
}


async def test_export_creates_persona_archive_files(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("u1", Dimension.SOUL, Layer.PRINCIPLE, "directness", [1], ["Q1"])

    paths = await export_markdown(db, "u1", tmp_path / "exports")

    assert {path.name for path in paths} == ARCHIVE_FILES
    for path in paths:
        assert path.exists()


async def test_dimension_files_only_include_matching_anchors(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("u1", Dimension.SOUL, Layer.PRINCIPLE, "directness", [1], ["Q1"])
    await db.save_anchor("u1", Dimension.SKILL, Layer.FACT, "debugging", [2], ["Q2"])

    await export_markdown(db, "u1", tmp_path / "exports")
    soul_text = (tmp_path / "exports" / "u1" / "SOUL.md").read_text(encoding="utf-8")
    skill_text = (tmp_path / "exports" / "u1" / "SKILL.md").read_text(encoding="utf-8")

    assert "# SOUL" in soul_text
    assert "dimension: SOUL" in soul_text
    assert "directness" in soul_text
    assert "debugging" not in soul_text
    assert "# SKILL" in skill_text
    assert "dimension: SKILL" in skill_text
    assert "debugging" in skill_text
    assert "directness" not in skill_text


async def test_dimension_files_separate_core_truths_and_emerging_patterns(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("u1", Dimension.SOUL, Layer.PRINCIPLE, "draft value", [1], ["Q1"])
    await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "confirmed value",
        [2, 3, 4],
        ["Q1", "Q2", "Q3"],
    )

    await export_markdown(db, "u1", tmp_path / "exports")
    text = (tmp_path / "exports" / "u1" / "SOUL.md").read_text(encoding="utf-8")

    assert "## Validated Patterns" in text
    assert "## Recurring but Unvalidated Patterns" in text
    assert "## Emerging Patterns" in text
    assert "confirmed value" in text
    assert "draft value" in text


async def test_same_session_three_question_anchor_is_not_validated_pattern(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    session = await db.get_or_create_session("u1", week=1)
    turns = [
        await db.save_turn(session.id, "user", "answer one"),
        await db.save_turn(session.id, "user", "answer two"),
        await db.save_turn(session.id, "user", "answer three"),
    ]
    await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "chooses direct truth when project risk is high",
        [turn.id for turn in turns],
        ["Q1", "Q2", "Q3"],
    )

    await export_markdown(db, "u1", tmp_path / "exports")
    text = (tmp_path / "exports" / "u1" / "SOUL.md").read_text(encoding="utf-8")
    validated_section = text.split("## Recurring but Unvalidated Patterns", 1)[0]

    assert "## Validated Patterns" in text
    assert "chooses direct truth" not in validated_section
    assert "chooses direct truth" in text.split("## Recurring but Unvalidated Patterns", 1)[1]
    assert "Promotion tier: recurring" in text
    assert "cross_session_evidence" in text


async def test_provenance_is_collapsed_under_anchor_items(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "confirmed value",
        [2, 3, 4],
        ["Q1", "Q2", "Q3"],
    )

    await export_markdown(db, "u1", tmp_path / "exports")
    text = (tmp_path / "exports" / "u1" / "SOUL.md").read_text(encoding="utf-8")

    assert "  > confirmed value" in text
    assert "<details>" in text
    assert "<summary>Provenance</summary>" in text
    assert "- Questions: Q1, Q2, Q3" in text
    assert "- Turns: 2, 3, 4" in text


async def test_anchor_markdown_cannot_break_export_structure(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "first line\n## Injected\n</details>\n<script>alert(1)</script>",
        [1],
        ["Q1"],
    )

    await export_markdown(db, "u1", tmp_path / "exports")
    text = (tmp_path / "exports" / "u1" / "SOUL.md").read_text(encoding="utf-8")

    assert "\n## Injected" not in text
    assert "</details>\n<script>" not in text
    assert "  > ## Injected" in text
    assert "  > &lt;/details&gt;" in text
    assert "  > &lt;script&gt;alert(1)&lt;/script&gt;" in text


async def test_export_writes_manifest_with_file_hashes(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("u1", Dimension.SOUL, Layer.PRINCIPLE, "directness", [1], ["Q1"])

    await export_markdown(db, "u1", tmp_path / "exports")
    target = tmp_path / "exports" / "u1"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    soul_text = (target / "SOUL.md").read_text(encoding="utf-8")
    soul_hash = hashlib.sha256(soul_text.encode("utf-8")).hexdigest()

    assert manifest["schema_version"] == "0.5"
    assert manifest["human_entrypoint"] == "START_HERE.md"
    assert manifest["technical_index"] == "index.md"
    assert set(manifest["archive_files"]) == ARCHIVE_FILES
    assert manifest["dimensions"]["SOUL"]["anchor_count"] == 1
    assert "manifest.json" not in manifest["payload_files"]
    assert manifest["payload_files"]["SOUL.md"]["sha256"] == f"sha256:{soul_hash}"


async def test_export_rescrubs_pii_at_output_boundary(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    async with aiosqlite.connect(db.path) as conn:
        await conn.execute(
            """
            INSERT INTO anchors(
                interviewee_id, dimension, layer, content,
                triangulated, source_turn_ids, source_question_ids
            )
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            ("u1", "SOUL", "fact", "Email john.doe@example.com", "[1]", '["Q1"]'),
        )
        await conn.commit()

    await export_markdown(db, "u1", tmp_path / "exports")
    text = (tmp_path / "exports" / "u1" / "SOUL.md").read_text(encoding="utf-8")

    assert "[EMAIL]" in text
    assert "john.doe@example.com" not in text
    assert "anchor_content_pii_scrubbed: true" in text


async def test_export_cli_with_explicit_db_does_not_require_api_key(tmp_path, monkeypatch):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("local", Dimension.SOUL, Layer.PRINCIPLE, "directness", [1], ["Q1"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(
        "sys.argv",
        [
            "virtualme.export",
            "--db",
            f"sqlite:///{db.path}",
            "--interviewee",
            "local",
            "--out",
            str(tmp_path / "exports"),
        ],
    )

    try:
        await main()
    except ValidationError as exc:
        raise AssertionError("explicit --db export should not require Settings") from exc

    assert (tmp_path / "exports" / "local" / "index.md").exists()
