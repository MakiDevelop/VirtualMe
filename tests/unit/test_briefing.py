from types import SimpleNamespace

from virtualme.interview.briefing import (
    INTERVIEW_PURPOSE,
    MAX_RENDER_CHARS,
    InterviewBriefing,
    build_interview_briefing,
)
from virtualme.interview.triples import PersonaTriple
from virtualme.storage.db import Anchor, Dimension, Layer, Session, Turn


class _BriefingDB:
    def __init__(self, *, recent_turns: list[Turn] | None = None):
        self.recent_turns = recent_turns or []

    async def load_anchors_summary(self, interviewee_id: str):
        anchors = []
        for index in range(15):
            anchors.append(
                Anchor(
                    interviewee_id=interviewee_id,
                    dimension=Dimension.STATE,
                    layer=Layer.PRINCIPLE if index % 2 == 0 else Layer.FACT,
                    content=f"anchor {index}",
                    triangulated=index >= 10,
                )
            )
        return {Dimension.STATE: anchors}

    async def load_triples(self, interviewee_id: str):
        relations = ["preference"] * 4 + ["skill"] * 4 + ["value_anchor"] * 4 + ["red_line"] * 4
        return [
            PersonaTriple(
                interviewee_id=interviewee_id,
                subject="interviewee",
                relation=relation,
                object=f"triple {index}",
                source_turn_ids=[index],
            )
            for index, relation in enumerate(relations)
        ]

    async def compute_coverage_gap(self, interviewee_id: str):
        return {dimension: index / 10 for index, dimension in enumerate(Dimension)}

    async def load_recent_turns(self, session_id: int, limit: int):
        return self.recent_turns[-limit:]


async def test_build_interview_briefing_applies_item_limits():
    turns = [
        Turn(id=index, session_id=1, role="user", content=f"turn {index}", content_hash="h")
        for index in range(10)
    ]

    briefing = await build_interview_briefing(
        _BriefingDB(recent_turns=turns),
        "u1",
        Session(id=1, interviewee_id="u1", week=2),
        max_week=5,
    )

    assert briefing.purpose == INTERVIEW_PURPOSE
    assert briefing.progress == "Week 2 of 5."
    assert briefing.durable_summary.count("- Anchor") == 12
    assert briefing.durable_summary.count("- Triple") == 12
    assert briefing.coverage_gaps.count("- ") == 8
    assert briefing.recent_transcript.count("受訪者:") == 8
    assert "anchor 14" in briefing.durable_summary
    assert "red_line" in briefing.durable_summary


def test_render_modes_include_expected_sections():
    briefing = InterviewBriefing(
        purpose=INTERVIEW_PURPOSE,
        progress="Week 1 of 3.",
        durable_summary="- durable",
        coverage_gaps="- gap",
        recent_transcript="受訪者: one\n訪談者: two\n受訪者: three\n訪談者: four\n受訪者: five",
    )

    full = briefing.render("full")
    classifier = briefing.render("classifier")
    anchor = briefing.render("anchor")

    assert "WHAT WE KNOW SO FAR:" in full
    assert "STILL TO COVER:" in full
    assert briefing.render("unknown") == full
    assert "WHAT WE KNOW SO FAR:" not in classifier
    assert "STILL TO COVER:" not in classifier
    assert "RECENT CONVERSATION:" in classifier
    assert "受訪者: one" not in anchor
    assert "訪談者: two" in anchor


def test_render_hard_limit_trims_recent_transcript_first():
    briefing = InterviewBriefing(
        purpose=INTERVIEW_PURPOSE,
        progress="Week 1 of 3.",
        durable_summary="- durable",
        coverage_gaps="- gap",
        recent_transcript="\n".join(f"受訪者: {'x' * 500}" for _ in range(40)),
    )

    rendered = briefing.render("full")

    assert len(rendered) <= MAX_RENDER_CHARS
    assert INTERVIEW_PURPOSE in rendered
    assert "PROGRESS:" in rendered
    assert "[truncated]" in rendered


async def test_build_interview_briefing_empty_state():
    class EmptyDB:
        async def load_anchors_summary(self, interviewee_id: str):
            return {}

        async def load_triples(self, interviewee_id: str):
            return []

        async def compute_coverage_gap(self, interviewee_id: str):
            return {}

        async def load_recent_turns(self, session_id: int, limit: int):
            return []

    briefing = await build_interview_briefing(
        EmptyDB(),
        "u1",
        SimpleNamespace(id=1, week=1),
        max_week=4,
    )

    assert briefing.durable_summary == "No durable signal extracted yet."
    assert briefing.coverage_gaps == "No computed coverage gaps yet."
    assert briefing.recent_transcript == "No recent conversation yet."
