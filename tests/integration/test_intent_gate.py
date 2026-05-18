import json

import aiosqlite
from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.interview.bot import process_turn
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB, Dimension, Question


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self):
        self.anchor_calls = 0
        self.depth_calls = 0
        self.follow_up_calls = 0

    async def create(self, **kwargs):
        max_tokens = kwargs["max_tokens"]
        prompt = kwargs["messages"][0]["content"]
        if max_tokens == 120:
            self.depth_calls += 1
            answer = prompt.split("Answer: ", 1)[1]
            text = json.dumps(self._assessment_for(answer))
        elif max_tokens == 500:
            self.anchor_calls += 1
            text = json.dumps(
                [
                    {
                        "dimension": "STATE",
                        "layer": "pattern",
                        "content": "專心寫 code 時工作狀態開心",
                    }
                ]
            )
        elif max_tokens == 80:
            self.follow_up_calls += 1
            text = "可以多說一點嗎？"  # noqa: RUF001
        elif max_tokens == 180:
            text = prompt.split("Ask this next: ", 1)[1]
        elif max_tokens == 900:
            text = (
                '[{"subject": "interviewee", "relation": "preference", '
                '"object": "direct flow", "source_turn_ids": [1], "confidence": 0.9}]'
            )
        else:
            text = "OK"
        return type("Response", (), {"content": [_Content(text)]})

    def _assessment_for(self, answer: str) -> dict[str, object]:
        if "directness" in answer:
            return {
                "kind": "THIN",
                "depth": "fact",
                "needs_follow_up": True,
                "confidence": 0.85,
            }
        if "工作很開心" in answer:
            return {
                "kind": "SUFFICIENT",
                "depth": "pattern",
                "needs_follow_up": False,
                "confidence": 0.9,
            }
        if "請用中文" in answer or answer.strip() == "繁體中文":
            return {
                "kind": "META",
                "depth": "fact",
                "needs_follow_up": False,
                "confidence": 0.95,
            }
        return {
            "kind": "EVASION",
            "depth": "fact",
            "needs_follow_up": False,
            "confidence": 0.9,
        }


class _Claude:
    def __init__(self):
        self.messages = _Messages()


class _FixedSelector:
    def __init__(self):
        self.next_question = Question(
            id="Q2",
            week=1,
            dimension=Dimension.SKILL,
            text="What skill matters most?",
        )
        self.question_pool = {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="請說說您最近的工作狀況。",
                ),
                self.next_question,
            ]
        }

    def select_next(self, *args, **kwargs):
        return self.next_question


async def test_dogfood_meta_and_evasion_do_not_extract_or_follow_up(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    selector = QuestionSelector(
        {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="請說說您最近的工作狀況。",
                )
            ]
        }
    )
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    claude = _Claude()
    session = await db.get_or_create_session("u1", week=1)
    await db.save_turn(session.id, "assistant", "請說說您最近的工作狀況。")

    await process_turn(
        "u1", "我最近工作很開心，專心寫 code", claude, db, selector, settings  # noqa: RUF001
    )
    assert claude.messages.anchor_calls == 1

    for message in [
        "請用中文與我訪談好嗎？",  # noqa: RUF001
        "繁體中文",
        "這是我母語啊，廢話",  # noqa: RUF001
        "這個問題和人格萃取有關嗎？我不希望浪費",  # noqa: RUF001
    ]:
        before_anchors = await _anchor_count(db)
        before_anchor_calls = claude.messages.anchor_calls
        before_follow_up_calls = claude.messages.follow_up_calls

        await process_turn("u1", message, claude, db, selector, settings)

        assert await _anchor_count(db) == before_anchors
        assert claude.messages.anchor_calls == before_anchor_calls
        assert claude.messages.follow_up_calls == before_follow_up_calls


async def test_closing_phrase_finalizes_before_intent_gate(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    selector = QuestionSelector(
        {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="請說說您最近的工作狀況。",
                )
            ]
        }
    )
    settings = Settings(
        anthropic_api_key=SecretStr("test"),
        use_ppa=False,
        persona_auto_export=True,
        persona_export_dir=str(tmp_path / "personas"),
    )
    claude = _Claude()

    reply = await process_turn("u1", "今天先這樣", claude, db, selector, settings)

    assert "今天先到這裡" in reply
    assert claude.messages.depth_calls == 0
    async with aiosqlite.connect(db.path) as conn:
        row = await (
            await conn.execute("SELECT status FROM sessions WHERE interviewee_id = ?", ("u1",))
        ).fetchone()
    assert row == ("completed",)
    assert (tmp_path / "personas" / "u1" / "SOUL.md").is_file()


async def test_thin_answer_can_probe_without_extracting_anchor(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    selector = QuestionSelector(
        {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="請說說您最近的工作狀況。",
                )
            ]
        }
    )
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    claude = _Claude()

    await process_turn("u1", "directness", claude, db, selector, settings)

    assert claude.messages.follow_up_calls == 1
    assert claude.messages.anchor_calls == 0
    assert await _anchor_count(db) == 0


async def test_first_evasion_bridges_then_consecutive_evasion_pauses(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    selector = _FixedSelector()
    settings = Settings(anthropic_api_key=SecretStr("test"), use_ppa=False)
    claude = _Claude()

    first_reply = await process_turn("u1", "不要問這個", claude, db, selector, settings)
    second_reply = await process_turn("u1", "還是不想答", claude, db, selector, settings)

    assert "這題如果不好說" in first_reply
    assert "請說說您最近的工作狀況。" in first_reply
    assert "先停" in second_reply
    async with aiosqlite.connect(db.path) as conn:
        row = await (
            await conn.execute("SELECT current_question_id FROM sessions WHERE interviewee_id = ?", ("u1",))
        ).fetchone()
    assert row == (None,)
    assert claude.messages.anchor_calls == 0
    assert claude.messages.follow_up_calls == 0


async def _anchor_count(db: DB) -> int:
    async with aiosqlite.connect(db.path) as conn:
        row = await (await conn.execute("SELECT COUNT(*) FROM anchors")).fetchone()
    return int(row[0])
