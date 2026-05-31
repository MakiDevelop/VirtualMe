import aiosqlite
from pydantic import ValidationError

from virtualme.blind_test.__main__ import main
from virtualme.blind_test.prepare import export_blind_test_prepare
from virtualme.blind_test.prepare import main as prepare_main
from virtualme.interview.blind_test import compute_accuracy, parse_results, verdict_for_accuracy
from virtualme.storage.db import DB, Dimension, Layer, Verdict


def test_parse_results_accepts_comma_separated_keyed_values():
    assert parse_results("T1=1,T2=0, T3=1") == {"T1": True, "T2": False, "T3": True}


def test_parse_results_rejects_invalid_values():
    try:
        parse_results("T1=1,T2=maybe")
    except ValueError as exc:
        assert "expected 0 or 1" in str(exc)
    else:
        raise AssertionError("invalid blind-test results should fail")


def test_parse_results_rejects_duplicate_keys():
    try:
        parse_results("T1=1,T1=0")
    except ValueError as exc:
        assert "duplicate result key" in str(exc)
    else:
        raise AssertionError("duplicate blind-test result keys should fail")


def test_verdict_thresholds_are_inclusive_for_ship_band():
    assert verdict_for_accuracy(0.4) == Verdict.OVERFIT_WARNING
    assert verdict_for_accuracy(0.5) == Verdict.SHIP_READY
    assert verdict_for_accuracy(0.6) == Verdict.SHIP_READY
    assert verdict_for_accuracy(0.7) == Verdict.NEEDS_WORK


def test_compute_accuracy_uses_correct_items_over_total():
    assert compute_accuracy({"T1": True, "T2": False, "T3": True}) == 2 / 3


async def test_save_blind_test_persists_result(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    blind_test_id = await db.save_blind_test(
        interviewee_id="u1",
        week=5,
        correctness_per_item={"T1": True, "T2": False, "T3": True},
        overall_accuracy=2 / 3,
        verdict=Verdict.NEEDS_WORK,
        weakest_dimension="VOICE.casual_mode",
        recommended_action="collect more casual voice samples",
    )

    assert blind_test_id > 0
    async with aiosqlite.connect(db.path) as conn:
        row = await (
            await conn.execute(
                """
                SELECT correctness_per_item, overall_accuracy, verdict,
                       weakest_dimension, recommended_action
                FROM blind_tests
                WHERE id = ?
                """,
                (blind_test_id,),
            )
        ).fetchone()

    assert row == (
        '{"T1": true, "T2": false, "T3": true}',
        2 / 3,
        "needs-work",
        "VOICE.casual_mode",
        "collect more casual voice samples",
    )


async def test_blind_test_cli_with_explicit_db_does_not_require_api_key(tmp_path, monkeypatch):
    db_path = tmp_path / "virtualme.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(
        "sys.argv",
        [
            "virtualme.blind_test",
            "--db",
            f"sqlite:///{db_path}",
            "--interviewee",
            "local",
            "--week",
            "5",
            "--results",
            "T1=1,T2=0,T3=1,T4=0,T5=1",
        ],
    )

    try:
        await main()
    except ValidationError as exc:
        raise AssertionError("explicit --db blind test should not require Settings") from exc

    async with aiosqlite.connect(db_path) as conn:
        row = await (
            await conn.execute(
                """
                SELECT overall_accuracy, verdict
                FROM blind_tests
                WHERE interviewee_id = 'local'
                """
            )
        ).fetchone()

    assert row == (0.6, "ship-ready")


async def test_blind_test_prepare_export_creates_three_files(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("local", Dimension.SOUL, Layer.PRINCIPLE, "directness", [1], ["Q1"])

    paths = await export_blind_test_prepare(db, "local", 5, tmp_path / "exports")

    assert {path.name for path in paths} == {
        "instructions.md",
        "scorecard.md",
        "persona-context.md",
    }
    assert all(path.exists() for path in paths)


async def test_blind_test_prepare_scorecard_has_week_five_rows(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    await export_blind_test_prepare(db, "local", 5, tmp_path / "exports")
    text = (tmp_path / "exports" / "local" / "week-5" / "scorecard.md").read_text(
        encoding="utf-8"
    )

    assert "| T1 |" in text
    assert "| T5 |" in text
    assert "| T6 |" not in text


async def test_blind_test_prepare_scorecard_has_week_eight_rows(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    await export_blind_test_prepare(db, "local", 8, tmp_path / "exports")
    text = (tmp_path / "exports" / "local" / "week-8" / "scorecard.md").read_text(
        encoding="utf-8"
    )

    assert "| T1 |" in text
    assert "| T8 |" in text


async def test_blind_test_prepare_persona_context_uses_recurring_unvalidated_language(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor("local", Dimension.SOUL, Layer.PRINCIPLE, "draft value", [1], ["Q1"])
    await db.save_anchor(
        "local",
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "confirmed value",
        [1, 2, 3],
        ["Q1", "Q2", "Q3"],
    )

    await export_blind_test_prepare(db, "local", 5, tmp_path / "exports")
    text = (tmp_path / "exports" / "local" / "week-5" / "persona-context.md").read_text(
        encoding="utf-8"
    )

    assert "confirmed value" in text
    assert "draft value" not in text
    assert "Legacy Recurring Principles" in text
    assert "legacy recurring/unvalidated" in text
    assert "validated traits" in text
    assert "Triangulated Principles" not in text


async def test_blind_test_prepare_rescrubs_pii_in_persona_context(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.save_anchor(
        "local",
        Dimension.PEOPLE,
        Layer.PRINCIPLE,
        "Email john.doe@example.com for review",
        [1, 2, 3],
        ["Q1", "Q2", "Q3"],
    )

    await export_blind_test_prepare(db, "local", 5, tmp_path / "exports")
    text = (tmp_path / "exports" / "local" / "week-5" / "persona-context.md").read_text(
        encoding="utf-8"
    )

    assert "[EMAIL]" in text
    assert "john.doe@example.com" not in text


async def test_blind_test_prepare_cli_with_explicit_db_does_not_require_api_key(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "virtualme.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(
        "sys.argv",
        [
            "virtualme.blind_test.prepare",
            "--db",
            f"sqlite:///{db_path}",
            "--interviewee",
            "local",
            "--week",
            "5",
            "--out",
            str(tmp_path / "exports"),
        ],
    )

    try:
        await prepare_main()
    except ValidationError as exc:
        raise AssertionError("explicit --db prepare should not require Settings") from exc

    assert (tmp_path / "exports" / "local" / "week-5" / "instructions.md").exists()


async def test_blind_test_prepare_rejects_invalid_week(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    try:
        await export_blind_test_prepare(db, "local", 9, tmp_path / "exports")
    except ValueError as exc:
        assert "--week must be between 1 and 8" in str(exc)
    else:
        raise AssertionError("invalid blind-test week should fail")
