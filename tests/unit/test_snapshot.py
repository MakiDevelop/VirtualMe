from pydantic import ValidationError

from virtualme.snapshot.__main__ import main
from virtualme.snapshot.core import (
    ConstructCard,
    EvidenceItem,
    _finalize_construct_card,
    apply_construct_card_reviews,
    build_snapshot_bundle,
    export_snapshot,
    export_snapshot_with_review,
    load_construct_card_reviews,
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
    assert "## Top-Level Sketch" in text
    assert "Communication surface: speaks bluntly" in text
    assert "Quality warning: all hypotheses are low confidence" in text
    assert "Low-confidence hypotheses: 1/1" in text
    assert "speaks bluntly" in text
    assert "Missing evidence" in text
    assert "Suggested follow-up" in text


async def test_snapshot_exports_construct_cards_file(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor("u1", Dimension.BOUNDARIES, Layer.PRINCIPLE, "rejects vague scope", [1], ["Q1"])

    paths = await export_snapshot(db, "u1", tmp_path / "exports")

    assert {path.name for path in paths} == {
        "construct-cards.md",
        "SOUL-lite.md",
        "mini-blind-test.md",
        "feedback-routing.md",
    }
    assert all(path.exists() for path in paths)


async def test_snapshot_export_rejects_path_traversal_interviewee_id(tmp_path):
    db = await _new_db(tmp_path)

    for bad_id in ["../x", "nested/x", "nested\\x", "bad\nid", "bad..id"]:
        try:
            await export_snapshot(db, bad_id, tmp_path / "exports")
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted unsafe interviewee_id: {bad_id!r}")


async def test_snapshot_review_ingestion_raises_card_to_plausible(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "uses project triangle language around budget scope and schedule",
        [1],
        ["Q1"],
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(
        """
        {
          "reviews": [
            {
              "card_id": "C1",
              "verdict": "like_me",
              "reviewer": "Maki",
              "reviewed_at": "2026-05-18",
              "concrete_case": "Used the constraint triangle to renegotiate an impossible delivery plan.",
              "exception_note": "Free discovery work can be an exception before the contract body.",
              "pressure_note": "Pushed back when hidden scope creep appeared.",
              "decision_tradeoff_note": "Trades short-term harmony for delivery realism.",
              "evidence_quality": "medium_high",
              "status_after_review": "plausible_after_human_review",
              "confidence_level": "plausible",
              "policy_status": "behavior_supported"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    paths = await export_snapshot_with_review(db, "u1", tmp_path / "exports", review_path)
    output_dir = tmp_path / "exports" / "u1" / "snapshot"
    cards = (output_dir / "construct-cards.md").read_text(encoding="utf-8")
    summary = (output_dir / "construct-card-review-summary.md").read_text(encoding="utf-8")

    assert {path.name for path in paths} == {
        "construct-cards.md",
        "SOUL-lite.md",
        "mini-blind-test.md",
        "feedback-routing.md",
        "construct-card-review-summary.md",
    }
    assert "- Confidence: plausible" in cards
    assert "- Policy status: behavior_supported" in cards
    assert "human review verdict=like_me" in cards
    assert "exception" not in next(
        line for line in cards.splitlines() if line.startswith("- Missing evidence:")
    )
    assert "| C1 | like_me | plausible | behavior_supported | medium_high |" in summary


async def test_markdown_review_ingestion_parses_persona_profile_style(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "uses project triangle language around budget scope and schedule",
        [1],
        ["Q1"],
    )
    review_path = tmp_path / "profile.md"
    review_path.write_text(
        """
        # Profile

        Reviewer: Maki

        ### C1 Constraint Triangle Integrity `confidence: plausible`
        - **When** trouble happens
        - 證據: Maki ratified this mechanism in the persona profile.
        """,
        encoding="utf-8",
    )

    reviews = load_construct_card_reviews(review_path)
    bundle = apply_construct_card_reviews(await build_snapshot_bundle(db, "u1"), reviews)
    card = bundle.construct_cards[0]

    assert reviews[0].verdict == "like_me"
    assert reviews[0].confidence_level == "plausible"
    assert card.confidence_level == "plausible"
    assert card.policy_status == "behavior_supported"
    assert card.confidence_checks["human_reviewed"] is True


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

    assert "| T1 | PEOPLE | A partner's reliability is uncertain" in blind
    assert "Which answer calibrates trust, risk, and responsibility more like the human?" in blind
    assert "Exact unlike-me phrase" in blind
    assert "Missing decision signal" in blind
    assert "Fallback from H1" in blind
    assert "mark PEOPLE as needing re-interview" in routing
    assert "Counterexample to collect" in routing
    assert "Pressure signal" in routing
    assert "Exception signal" in routing
    assert "Exact wording signal" in routing
    assert "Decision tradeoff signal" in routing
    assert "Ask what evidence makes them increase or reduce trust." in routing


async def test_mini_blind_test_varies_skill_scenarios_by_evidence(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.SKILL,
        Layer.PATTERN,
        "uses project triangle language around budget scope and schedule",
        [1],
        ["Q1"],
    )
    await db.save_anchor(
        "u1",
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "treats handoff quality as proof of real commitment",
        [2],
        ["Q2"],
    )
    await db.save_anchor(
        "u1",
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "spots emotional blackmail during pricing negotiation",
        [3],
        ["Q3"],
    )

    bundle = await build_snapshot_bundle(db, "u1")
    scenarios = [item.scenario for item in bundle.mini_blind_test]

    assert any("family event" in scenario for scenario in scenarios)
    assert any("community kitchen" in scenario for scenario in scenarios)
    assert any("relative" in scenario and "shared trip" in scenario for scenario in scenarios)
    assert all("budget scope and schedule" not in scenario for scenario in scenarios)
    assert len(set(scenarios)) == len(scenarios)


async def test_construct_card_triangle_schema_and_confidence_rules(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "uses project triangle language around budget scope and schedule",
        [1],
        ["Q1"],
    )

    bundle = await build_snapshot_bundle(db, "u1")

    assert bundle.construct_cards
    card = bundle.construct_cards[0]
    assert card.trigger_context
    assert card.protected_value == "delivery realism"
    assert card.falsifier
    assert "exception" in card.missing_evidence
    assert card.extraction_method == "rule_based"
    assert card.confidence_level == "draft"
    assert card.confidence_checks["multi_anchor_support"] is False
    assert card.policy_status == "espoused_only"
    assert card.exception_rule is None
    assert "exception" in card.feedback_routes
    assert card.decision_rule != "uses project triangle language around budget scope and schedule"


async def test_soul_lite_adds_synthesized_patterns_and_demotes_raw_appendix(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "uses project triangle language around budget scope and schedule",
        [1],
        ["Q1"],
    )

    text = render_soul_lite(await build_snapshot_bundle(db, "u1"))

    assert "## Synthesized Patterns" in text
    assert "Constraint triangle integrity" in text
    assert "## Raw Hypotheses Appendix" in text
    assert "These are source-level hypotheses retained for audit" in text


async def test_feedback_routing_includes_construct_missing_evidence_categories(tmp_path):
    db = await _new_db(tmp_path)
    await db.save_anchor(
        "u1",
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "uses project triangle language around budget scope and schedule",
        [1],
        ["Q1"],
    )

    bundle = await build_snapshot_bundle(db, "u1")
    routing = render_feedback_routing(bundle)

    assert "Construct Card Routes" in routing
    assert "Construct-card missing evidence route: exception." in routing
    assert "Construct-card missing evidence route: decision_tradeoff." in routing


def test_raw_wrapper_risk_caps_construct_card_confidence():
    card = ConstructCard(
        id="C0",
        title="Raw wrapper",
        decision_rule="protect direct truth by choosing direct truth",
        trigger_context="direct truth",
        protected_value="direct truth",
        traded_value=None,
        default_action="choose direct truth",
        refused_action=None,
        exception_rule=None,
        register=None,
        falsifier="Would not choose direct truth.",
        supporting_evidence=[
            EvidenceItem(
                kind="anchor",
                dimension=Dimension.SOUL,
                layer=Layer.PRINCIPLE,
                content="direct truth choose direct truth protect direct truth",
            )
        ],
        disconfirming_evidence=[],
        source_anchor_ids=[],
        source_turn_ids=[],
        source_question_ids=[],
        dimension_tags=[Dimension.SOUL],
        confidence_level="draft",
        confidence_reason="",
        confidence_checks={},
        missing_evidence=[],
        blind_test_probe=None,
        feedback_routes=[],
        extraction_method="rule_based",
        policy_status="espoused_only",
        stability_scope=None,
        context_dependence=None,
        exception_archetype=None,
    )

    finalized = _finalize_construct_card(card)

    assert finalized.confidence_level == "insufficient"
    assert finalized.confidence_checks["raw_wrapper_safe"] is False


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


async def test_snapshot_cli_accepts_review_artifact(tmp_path, monkeypatch):
    db_path = tmp_path / "virtualme.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    db = DB(str(db_path))
    await db.init()
    await db.save_anchor(
        "local",
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "uses project triangle language around budget scope and schedule",
        [1],
        ["Q1"],
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(
        """
        {
          "reviews": [
            {
              "card_id": "C1",
              "verdict": "like_me",
              "confidence_level": "plausible",
              "evidence_quality": "medium",
              "status_after_review": "plausible_after_human_review"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
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
            "--review",
            str(review_path),
        ],
    )

    await main()

    snapshot_dir = tmp_path / "exports" / "local" / "snapshot"
    assert (snapshot_dir / "construct-card-review-summary.md").exists()
    assert "plausible_after_human_review" in (
        snapshot_dir / "construct-cards.md"
    ).read_text(encoding="utf-8")
