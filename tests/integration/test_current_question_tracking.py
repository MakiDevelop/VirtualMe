import json

import aiosqlite
from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.interview.bot import process_turn
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB, Dimension, Layer, Question


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self, depth: str = "principle", reasoner_payload: dict | None = None):
        self.depth = depth
        self.reasoner_payload = reasoner_payload
        self.depth_questions: list[str] = []
        self.ppa_calls = 0

    async def create(self, **kwargs):
        max_tokens = kwargs["max_tokens"]
        prompt = kwargs["messages"][0]["content"]
        if max_tokens == 120:
            question = prompt.split("Question: ", 1)[1].split("\n", 1)[0]
            self.depth_questions.append(question)
            text = json.dumps(
                {
                    "kind": "SUFFICIENT",
                    "depth": self.depth,
                    "needs_follow_up": self.depth != "principle",
                    "confidence": 0.9,
                }
            )
        elif max_tokens == 500:
            question = prompt.split("Question: ", 1)[1].split("\n", 1)[0]
            text = json.dumps(
                [
                    {
                        "dimension": "SKILL" if "skill" in question.lower() else "STATE",
                        "layer": "principle",
                        "content": "directness over deference",
                    }
                ]
            )
        elif max_tokens == 80:
            text = "Could you give me one concrete example?"
        elif max_tokens == 180:
            text = prompt.split("Ask this next: ", 1)[1]
        elif max_tokens == 150:
            self.ppa_calls += 1
            text = '{"assistant": "freeform ppa reply"}'
        elif max_tokens == 900 and self.reasoner_payload is not None:
            text = json.dumps(self.reasoner_payload)
        else:
            text = "OK"
        return type("Response", (), {"content": [_Content(text)]})


class _Claude:
    def __init__(self, depth: str = "principle", reasoner_payload: dict | None = None):
        self.messages = _Messages(depth, reasoner_payload)


class _FixedSelector:
    def __init__(self, next_question: Question | None):
        self.question_pool = {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="How has work been?",
                ),
                Question(
                    id="Q2",
                    week=1,
                    dimension=Dimension.SKILL,
                    text="What skill matters most?",
                ),
            ]
        }
        self.next_question = next_question

    def select_next(self, *args, **kwargs):
        return self.next_question


async def _session_current_question_id(db: DB, session_id: int) -> str | None:
    async with aiosqlite.connect(db.path) as conn:
        row = await (
            await conn.execute(
                "SELECT current_question_id FROM sessions WHERE id = ?",
                (session_id,),
            )
        ).fetchone()
    return row[0] if row else None


async def test_next_question_is_used_as_subsequent_answer_context(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    q2 = Question(
        id="Q2",
        week=1,
        dimension=Dimension.SKILL,
        text="What skill matters most?",
    )
    selector = _FixedSelector(q2)
    claude = _Claude()

    await process_turn("u1", "First answer.", claude, db, selector, settings)
    assert await _session_current_question_id(db, 1) == "Q2"

    await process_turn("u1", "Second answer.", claude, db, selector, settings)

    assert claude.messages.depth_questions == [
        "How has work been?",
        "What skill matters most?",
    ]
    summary = await db.load_anchors_summary("u1")
    assert summary[Dimension.SKILL][0].source_question_ids == ["Q2"]


async def test_follow_up_branch_does_not_advance_current_question(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    q2 = Question(
        id="Q2",
        week=1,
        dimension=Dimension.SKILL,
        text="What skill matters most?",
    )
    selector = _FixedSelector(q2)
    claude = _Claude(depth="fact")
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "Q2")

    await process_turn("u1", "A short fact.", claude, db, selector, settings)

    assert await _session_current_question_id(db, session.id) == "Q2"


async def test_follow_up_branch_still_extracts_anchor(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    q2 = Question(
        id="Q2",
        week=1,
        dimension=Dimension.SKILL,
        text="What skill matters most?",
    )
    selector = _FixedSelector(q2)
    claude = _Claude(depth="fact")
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "Q2")

    await process_turn("u1", "A short fact.", claude, db, selector, settings)

    summary = await db.load_anchors_summary("u1")
    assert summary[Dimension.SKILL][0].content == "directness over deference"
    assert summary[Dimension.SKILL][0].source_question_ids == ["Q2"]


async def test_selector_none_does_not_persist_default_question(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    selector = _FixedSelector(None)
    claude = _Claude()
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "Q2")

    await process_turn("u1", "Answer while selector returns none.", claude, db, selector, settings)

    assert await _session_current_question_id(db, session.id) == "Q2"


async def test_probe_budget_forces_advance_to_next_question(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    selector = QuestionSelector(
        {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="How has work been?",
                ),
                Question(
                    id="Q2",
                    week=1,
                    dimension=Dimension.SKILL,
                    text="What skill matters most?",
                ),
            ]
        }
    )
    claude = _Claude(depth="fact")

    await process_turn("u1", "First thin answer.", claude, db, selector, settings)
    await process_turn("u1", "Second thin answer.", claude, db, selector, settings)
    reply = await process_turn("u1", "Third thin answer.", claude, db, selector, settings)

    assert reply == "What skill matters most?"
    assert await _session_current_question_id(db, 1) == "Q2"


async def test_ppa_does_not_override_explicit_next_question(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=True)
    q2 = Question(
        id="Q2",
        week=1,
        dimension=Dimension.SKILL,
        text="What skill matters most?",
    )
    selector = _FixedSelector(q2)
    claude = _Claude()

    reply = await process_turn("u1", "Sufficient answer.", claude, db, selector, settings)

    assert reply == "What skill matters most?"
    assert claude.messages.ppa_calls == 0


async def test_reasoner_path_extracts_anchors_and_advances_with_explicit_next_question(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(
        anthropic_api_key=SecretStr("test"),
        use_ppa=False,
        reasoning_turn_enabled=True,
        reasoning_test_user_ids="u1",
    )
    q2 = Question(
        id="Q2",
        week=1,
        dimension=Dimension.SKILL,
        text="What skill matters most?",
    )
    selector = _FixedSelector(q2)
    claude = _Claude(
        reasoner_payload={
            "read": "user gave evidence",
            "boundary_status": "none",
            "engagement_state": "engaged",
            "next_move": "advance",
            "next_question_id": "Q2",
            "should_echo": False,
            "echo_content": None,
            "reflection_note": None,
            "reply": "Next.",
        }
    )

    reply = await process_turn("u1", "Sufficient answer.", claude, db, selector, settings)

    assert reply == "Next."
    assert await _session_current_question_id(db, 1) == "Q2"
    summary = await db.load_anchors_summary("u1")
    assert summary[Dimension.STATE][0].content == "directness over deference"
    assert summary[Dimension.STATE][0].source_question_ids == ["Q1"]


async def test_reasoner_path_falls_back_to_weakest_shallow_question_when_advance_has_no_id(
    tmp_path,
):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(
        anthropic_api_key=SecretStr("test"),
        use_ppa=False,
        reasoning_turn_enabled=True,
        reasoning_test_user_ids="u1",
    )
    selector = QuestionSelector(
        {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="How has work been?",
                ),
                Question(
                    id="Q2",
                    week=1,
                    dimension=Dimension.SKILL,
                    text="What skill matters most?",
                ),
                Question(
                    id="Q3",
                    week=1,
                    dimension=Dimension.VOICE,
                    text="How do you usually speak under pressure?",
                ),
            ]
        }
    )
    for index in range(3):
        await db.save_anchor("u1", Dimension.SKILL, Layer.FACT, f"skill-{index}", [1], ["QS"])
    claude = _Claude(
        reasoner_payload={
            "read": "user gave evidence",
            "boundary_status": "none",
            "engagement_state": "engaged",
            "next_move": "advance",
            "next_question_id": None,
            "should_echo": False,
            "echo_content": None,
            "reflection_note": None,
            "reply": "Next.",
        }
    )

    await process_turn("u1", "Sufficient answer.", claude, db, selector, settings)

    assert await _session_current_question_id(db, 1) == "Q3"


async def test_reasoner_path_does_not_extract_on_explicit_refusal(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    settings = Settings(
        anthropic_api_key=SecretStr("test"),
        use_ppa=False,
        reasoning_turn_enabled=True,
        reasoning_test_user_ids="u1",
    )
    selector = _FixedSelector(None)
    claude = _Claude(
        reasoner_payload={
            "read": "user refused",
            "boundary_status": "explicit_refusal",
            "engagement_state": "guarded",
            "next_move": "honor_skip",
            "next_question_id": None,
            "should_echo": False,
            "echo_content": None,
            "reflection_note": None,
            "reply": "我們先跳過。",
        }
    )

    reply = await process_turn("u1", "不想回答", claude, db, selector, settings)

    assert reply == "我們先跳過。"
    summary = await db.load_anchors_summary("u1")
    assert all(not anchors for anchors in summary.values())
