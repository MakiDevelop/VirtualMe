import aiosqlite
from pydantic import ValidationError

from virtualme.export.__main__ import main
from virtualme.export.markdown import export_markdown
from virtualme.storage.db import DB, Dimension, Layer


async def test_export_creates_three_files(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("u1", Dimension.SOUL, Layer.PRINCIPLE, "directness", [1], ["Q1"])

    paths = await export_markdown(db, "u1", tmp_path / "exports")

    assert {path.name for path in paths} == {"index.md", "anchors.md", "principles.md"}
    for path in paths:
        assert path.exists()


async def test_anchors_are_grouped_by_dimension(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("u1", Dimension.SOUL, Layer.PRINCIPLE, "directness", [1], ["Q1"])
    await db.save_anchor("u1", Dimension.SKILL, Layer.FACT, "debugging", [2], ["Q2"])

    await export_markdown(db, "u1", tmp_path / "exports")
    text = (tmp_path / "exports" / "u1" / "anchors.md").read_text(encoding="utf-8")

    assert "## SOUL" in text
    assert "## SKILL" in text
    assert "directness" in text
    assert "debugging" in text


async def test_principles_only_include_triangulated_anchors(tmp_path):
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
    text = (tmp_path / "exports" / "u1" / "principles.md").read_text(encoding="utf-8")

    assert "confirmed value" in text
    assert "draft value" not in text


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
    text = (tmp_path / "exports" / "u1" / "anchors.md").read_text(encoding="utf-8")

    assert "[EMAIL]" in text
    assert "john.doe@example.com" not in text


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
