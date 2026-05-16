from pydantic import ValidationError

from virtualme.snapshot.__main__ import main
from virtualme.snapshot.core import (
    build_snapshot_bundle,
    export_snapshot,
    render_feedback_routing,
    render_mini_blind_test,
    render_soul_lite,
)
from virtualme.storage.db import DB, Dimension, Layer


async def _new_db(tmp_path) -> DB:
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    return db


async def test_build_snapshot_prefers_triangulated_decision_anchors(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "I choose direct truth over keeping peace when project risk is high",
        [1, 2, 3],
        ["Q1", "Q2", "Q3"],
    )
    await db.save_anchor("u1", Dimension.STATE, Layer.FACT, "tired this week", [4], ["Q4"])

    bundle = await build_snapshot_bundle(db, "u1")

    assert bundle.hypotheses
    first = bundle.hypotheses[0]
    assert first.dimension == Dimension.SOUL
    assert first.confidence == "high"
    assert first.needs_verification is False
    assert "direct truth" in first.hypothesis
    assert first.evidence[0].source_question_ids == ["Q1", "Q2", "Q3"]


async def test_snapshot_uses_triples_when_anchors_are_sparse(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_triple(
        {
            "interviewee_id": "u1",
            "subject": "interviewee",
            "relation": "red_line",
            "object": "refuses projects where scope and budget cannot be reconciled",
            "source_turn_ids": [10],
            "confidence": 0.8,
        }
    )

    bundle = await build_snapshot_bundle(db, "u1")

    assert bundle.hypotheses
    assert bundle.hypotheses[0].dimension == Dimension.BOUNDARIES
    assert "scope and budget" in bundle.hypotheses[0].hypothesis


async def test_render_soul_lite_marks_hypotheses_as_draft(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor("u1", Dimension.VOICE, Layer.PATTERN, "speaks bluntly", [1], ["Q1"])

    bundle = await build_snapshot_bundle(db, "u1")
    text = render_soul_lite(bundle)

    assert "hypothesis draft" in text
    assert "speaks bluntly" in text
    assert "Missing evidence" in text
    assert "Suggested follow-up" in text


async def test_snapshot_exports_three_files(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor("u1", Dimension.BOUNDARIES, Layer.PRINCIPLE, "rejects vague scope", [1], ["Q1"])

    paths = await export_snapshot(db, "u1", tmp_path / "exports")

    assert {path.name for path in paths} == {
        "SOUL-lite.md",
        "mini-blind-test.md",
        "feedback-routing.md",
    }
    assert all(path.exists() for path in paths)


async def test_mini_blind_test_and_feedback_routing_reference_hypotheses(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.PEOPLE,
        Layer.PRINCIPLE,
        "trusts people who proactively report risk",
        [1, 2, 3],
        ["Q1", "Q2", "Q3"],
    )

    bundle = await build_snapshot_bundle(db, "u1")
    blind = render_mini_blind_test(bundle)
    routing = render_feedback_routing(bundle)

    assert "| T1 | PEOPLE |" in blind
    assert "Based on H1" in blind
    assert "mark PEOPLE as needing re-interview" in routing


async def test_snapshot_rescrubs_pii(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.PEOPLE,
        Layer.FACT,
        "Email john.doe@example.com when risk appears",
        [1],
        ["Q1"],
    )

    bundle = await build_snapshot_bundle(db, "u1")
    text = render_soul_lite(bundle)

    assert "[EMAIL]" in text
    assert "john.doe@example.com" not in text


async def test_snapshot_cli_with_explicit_db_does_not_require_api_key(tmp_path, monkeypatch):
    db_path = tmp_path / "virtualme.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    db = DB(str(db_path))
    await db.init()
    await db.save_anchor("local", Dimension.SOUL, Layer.PRINCIPLE, "values directness", [1], ["Q1"])
    monkeypatch.setattr(
        "sys.argv",
        [
            "virtualme.snapshot",
            "--db",
            f"sqlite:///{db_path}",
            "--interviewee",
            "local",
            "--out",
            str(tmp_path / "exports"),
        ],
    )

    try:
        await main()
    except ValidationError as exc:
        raise AssertionError("explicit --db snapshot should not require Settings") from exc

    assert (tmp_path / "exports" / "local" / "snapshot" / "SOUL-lite.md").exists()
