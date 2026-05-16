"""Tests for BW7 interview command detection (status query / re-talk)."""

import json

from pydantic import SecretStr

from virtualme.config import Settings
from virtualme.interview.bot import process_turn
from virtualme.interview.commands import RestartRequest, RetalkRequest, StatusQuery, detect_command
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB, Dimension, Layer, Question

# --- detect_command pure tests -----------------------------------------------


def test_detect_status_query():
    assert isinstance(detect_command("現在在問什麼"), StatusQuery)
    assert isinstance(detect_command("我們收集到哪一塊了"), StatusQuery)
    assert isinstance(detect_command("萃取進度"), StatusQuery)
    assert isinstance(detect_command("有哪些主題"), StatusQuery)
    assert isinstance(detect_command("目前訪談的進度如何" + "\uff1f"), StatusQuery)
    assert isinstance(detect_command("上面的訪談是針對哪一個人格主題" + "\uff1f"), StatusQuery)
    assert isinstance(detect_command("which dimension are we on"), StatusQuery)


def test_detect_restart_request():
    assert isinstance(detect_command("重頭開始萃取"), RestartRequest)
    assert isinstance(detect_command("從頭開始"), RestartRequest)


def test_detect_retalk_with_dimension():
    command = detect_command("我想重談人際關係")
    assert isinstance(command, RetalkRequest)
    assert command.dimension == Dimension.PEOPLE


def test_detect_retalk_without_dimension():
    command = detect_command("可以重談嗎")
    assert isinstance(command, RetalkRequest)
    assert command.dimension is None


def test_normal_answer_is_not_a_command():
    assert detect_command("When the migration started I preferred short questions.") is None
    assert detect_command("我覺得最近工作還算順利") is None


def test_long_answer_with_keyword_is_not_a_command():
    # A long storytelling answer that happens to contain "重談" must not trigger.
    long_answer = "重談 " + "這是一段很長的訪談回答內容描述當時的情境與感受" * 3
    assert len(long_answer) > 40
    assert detect_command(long_answer) is None


# --- process_turn integration ------------------------------------------------


async def _new_db(tmp_path) -> DB:
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    return db


async def test_process_turn_status_query_reports_current_dimension(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="How has work been?")]}
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))

    reply = await process_turn("u1", "現在在問什麼", object(), db, selector, settings)

    assert "近況" in reply  # STATE label
    assert "八大萃取主題" in reply
    assert "總完成度" in reply
    assert "語氣・表達" in reply
    assert "界線・原則" in reply
    turns = await db.load_session_turns(1)
    assert len(turns) == 2  # turn pair saved, no extraction
    assert await db.load_anchors_summary("u1") == {} or not await db.load_triples("u1")


async def test_process_turn_status_query_reports_completion_progress(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="QV", week=1, dimension=Dimension.VOICE, text="Voice question")]}
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    await db.save_anchor("u1", Dimension.VOICE, Layer.PRINCIPLE, "plain voice", [1], ["QV"])
    await db.save_anchor(
        "u1",
        Dimension.BOUNDARIES,
        Layer.PRINCIPLE,
        "no private details",
        [1],
        ["Q1", "Q2", "Q3"],
    )
    await db.save_anchor("u1", Dimension.BOUNDARIES, Layer.FACT, "privacy boundary", [2], ["Q4"])
    await db.save_anchor("u1", Dimension.BOUNDARIES, Layer.FACT, "human review", [3], ["Q5"])

    reply = await process_turn("u1", "萃取進度", object(), db, selector, settings)

    assert "語氣・表達: 33%" in reply
    assert "界線・原則: 100%" in reply
    assert "目前最缺" in reply


async def test_process_turn_restart_archives_old_run_and_starts_week_one(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="How has work been?",
                )
            ]
        }
    )
    settings = Settings(
        anthropic_api_key=SecretStr("k"),
        persona_export_dir=str(tmp_path / "personas"),
    )
    old_session = await db.get_or_create_session("u1", week=1)
    await db.save_turn(old_session.id, "assistant", "old question")
    await db.save_anchor("u1", Dimension.VOICE, Layer.PRINCIPLE, "old voice", [1], ["Q1"])
    await db.save_triple(
        {
            "interviewee_id": "u1",
            "subject": "interviewee",
            "relation": "preference",
            "object": "old memory",
            "source_turn_ids": [1],
            "confidence": 0.9,
        }
    )

    reply = await process_turn("u1", "重頭開始萃取", _Claude(), db, selector, settings)

    assert "從頭開始萃取" in reply
    assert "舊資料已封存" in reply
    assert "繁中第一題" in reply
    assert "How has work been?" not in reply
    assert await db.load_anchors_summary("u1") == {dimension: [] for dimension in Dimension}
    assert await db.load_triples("u1") == []
    assert (tmp_path / "personas" / "u1" / "VOICE.md").is_file()

    async with db._connect() as conn:
        sessions = await (
            await conn.execute(
                "SELECT id, week, status, current_question_id FROM sessions "
                "WHERE interviewee_id = ? ORDER BY id",
                ("u1",),
            )
        ).fetchall()

    assert sessions[0][1] == -old_session.id
    assert sessions[0][2] == "archived"
    assert sessions[-1][1] == 1
    assert sessions[-1][2] == "active"
    assert sessions[-1][3] == "Q1"


async def test_light_greeting_after_restart_does_not_replay_restart_ack(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {
            1: [
                Question(
                    id="Q1",
                    week=1,
                    dimension=Dimension.STATE,
                    text="How has work been?",
                )
            ]
        }
    )
    settings = Settings(
        anthropic_api_key=SecretStr("k"),
        persona_export_dir=str(tmp_path / "personas"),
    )

    restart_reply = await process_turn("u1", "重頭開始萃取", _Claude(), db, selector, settings)
    reply = await process_turn("u1", "哈囉", _Claude(), db, selector, settings)

    assert "從頭開始萃取" in restart_reply
    assert "才剛開始" in reply
    assert "剛才問的是" not in reply
    assert "封存摘要" not in reply
    assert "從頭開始萃取" not in reply
    assert "繁中第一題" in reply


async def test_process_turn_light_greeting_starts_first_question(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="How has work been?")]}
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))

    reply = await process_turn("u1", "哈囉", _Claude(), db, selector, settings)

    assert "才剛開始" in reply
    assert "近況" in reply
    assert "繁中第一題" in reply
    assert await db.get_current_question_id(1) == "Q1"
    turns = await db.load_session_turns(1)
    assert [turn.role for turn in turns] == ["user", "assistant"]


async def test_process_turn_greeting_with_trailing_punctuation_resumes(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="How has work been?")]}
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))

    reply = await process_turn("u1", "哈囉" + "\uff5e", _Claude(), db, selector, settings)

    assert "才剛開始" in reply
    assert "近況" in reply
    assert "我先記下這點" not in reply


async def test_process_turn_light_greeting_resumes_known_progress(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {
            1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="State question")],
            2: [Question(id="QV", week=2, dimension=Dimension.VOICE, text="Voice question")],
        }
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "QV")
    await db.save_turn(session.id, "assistant", "請談談你的說話方式。")

    reply = await process_turn("u1", "哈囉", _Claude(), db, selector, settings)

    assert "才剛開始" in reply
    assert "語氣・表達" in reply
    assert "剛才問的是" in reply
    assert "請談談你的說話方式。" in reply
    assert await db.get_current_question_id(session.id) == "QV"


async def test_process_turn_light_greeting_cleans_old_bridge_prefix(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.HISTORY, text="History question")]}
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "Q1")
    await db.save_turn(
        session.id,
        "assistant",
        "可以" + "\uff0c" + "我先記下這點。我們回到剛才這題。\n真正的問題",
    )

    reply = await process_turn("u1", "哈囉", _Claude(), db, selector, settings)

    assert "人生歷程" in reply
    assert "真正的問題" in reply
    assert "我先記下這點" not in reply


async def test_process_turn_light_greeting_rerenders_stored_placeholder_question(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.BOUNDARIES, text="Clean question")]}
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "Q1")
    await db.save_turn(
        session.id,
        "assistant",
        "當你要回推 {decision_partner} 時 把你會用的原話講給我聽。",
    )

    reply = await process_turn("u1", "哈囉", _Claude(), db, selector, settings)

    assert "{decision_partner}" not in reply
    assert "剛才問的是" not in reply
    assert "界線・原則" in reply
    assert "繁中第一題" in reply


async def test_process_turn_light_greeting_mid_progress_asks_to_continue(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.VOICE, text="Voice question")]}
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "Q1")
    await db.save_turn(session.id, "assistant", "請談談你的說話方式。")
    for dimension in (Dimension.VOICE, Dimension.BOUNDARIES, Dimension.SKILL):
        for index in range(3):
            await db.save_anchor("u1", dimension, Layer.FACT, f"{dimension}-{index}", [1], ["Q1"])

    reply = await process_turn("u1", "哈囉", _Claude(), db, selector, settings)

    assert "完成一大段" in reply
    assert "方便繼續嗎" in reply
    assert "請談談你的說話方式。" in reply


async def test_process_turn_light_greeting_high_progress_encourages_finish(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {1: [Question(id="Q1", week=1, dimension=Dimension.BOUNDARIES, text="Boundaries question")]}
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "Q1")
    await db.save_turn(session.id, "assistant", "請談談你的界線。")
    for dimension in Dimension:
        if dimension == Dimension.STATE:
            continue
        for index in range(3):
            await db.save_anchor("u1", dimension, Layer.FACT, f"{dimension}-{index}", [1], ["Q1"])

    reply = await process_turn("u1", "哈囉", _Claude(), db, selector, settings)

    assert "快完成了" in reply
    assert "再收一點關鍵細節" in reply
    assert "請談談你的界線。" in reply


async def test_status_query_after_pause_does_not_advance_question(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {
            1: [
                Question(id="Q1", week=1, dimension=Dimension.HISTORY, text="History question"),
                Question(id="Q2", week=1, dimension=Dimension.PEOPLE, text="People question"),
            ]
        }
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "Q1")
    await db.save_turn(
        session.id,
        "assistant",
        "好, 這題我們先停在這裡。如果你想換題、休息一下, 或指定要談哪一塊, 直接跟我說。",
    )

    reply = await process_turn("u1", "目前訪談的進度如何?", _Claude(), db, selector, settings)

    assert "總完成度" in reply
    assert "People question" not in reply
    assert await db.get_current_question_id(session.id) == "Q1"


async def test_status_query_uses_current_question_dimension_not_last_assistant_text(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {
            1: [
                Question(id="QH", week=1, dimension=Dimension.HISTORY, text="History question"),
                Question(id="QS", week=1, dimension=Dimension.SKILL, text="Skill question"),
            ]
        }
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    session = await db.get_or_create_session("u1", week=1)
    await db.set_current_question_id(session.id, "QS")
    await db.save_turn(session.id, "assistant", "我們目前在【人生歷程】這一塊。")

    reply = await process_turn("u1", "上面的訪談是針對哪一個人格主題?", _Claude(), db, selector, settings)

    assert "我們現在正在收集的人格維度是【專業技能】" in reply
    assert "人生歷程: 0%" in reply
    assert "人生歷程: 0% (0 anchors, 0 confirmed) ← 目前" not in reply


async def test_process_turn_retalk_pins_dimension_question(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {
            1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="State question")],
            2: [Question(id="QV", week=2, dimension=Dimension.VOICE, text="Voice question here")],
        }
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))

    reply = await process_turn("u1", "重談 語氣", object(), db, selector, settings)

    assert "語氣" in reply
    assert "Voice question here" in reply
    assert "封存" in reply
    assert await db.get_current_question_id(1) == "QV"


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    async def create(self, **kwargs):
        max_tokens = kwargs["max_tokens"]
        if max_tokens == 120:
            text = json.dumps(
                {
                    "kind": "SUFFICIENT",
                    "depth": "principle",
                    "needs_follow_up": False,
                    "confidence": 0.9,
                }
            )
        elif max_tokens in (500, 900):
            text = "[]"
        else:
            text = "繁中第一題"
        return type("Response", (), {"content": [_Content(text)]})


class _Claude:
    def __init__(self):
        self.messages = _Messages()


async def test_retalk_then_normal_answer_runs_without_error(tmp_path):
    # Regression: a normal interview answer right after a re-talk command must
    # not break. (Codex review BW7-12 alleged a SQLite syntax error here; this
    # test exercises that exact path and confirms it does not occur.)
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {
            1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="State question")],
            2: [Question(id="QV", week=2, dimension=Dimension.VOICE, text="Voice question here")],
        }
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    claude = _Claude()

    retalk_reply = await process_turn("u1", "重談 語氣", claude, db, selector, settings)
    assert await db.get_current_question_id(1) == "QV"  # re-talk pinned VOICE

    # The next normal answer must process cleanly (no SQLite error) — it is
    # answered against the pinned QV before the selector advances.
    reply = await process_turn("u1", "我說話通常很直接不拐彎", claude, db, selector, settings)

    assert retalk_reply and reply
    turns = await db.load_session_turns(1)
    assert len(turns) >= 4  # retalk pair + normal answer pair


async def test_retalk_archives_dimension_anchors_and_resets_question_state(tmp_path):
    db = await _new_db(tmp_path)
    selector = QuestionSelector(
        {
            1: [Question(id="Q1", week=1, dimension=Dimension.STATE, text="State question")],
            2: [Question(id="QV", week=2, dimension=Dimension.VOICE, text="Voice question here")],
        }
    )
    settings = Settings(anthropic_api_key=SecretStr("k"))
    await db.save_anchor("u1", Dimension.VOICE, Layer.PRINCIPLE, "old voice", [1], ["QV"])
    await db.save_anchor("u1", Dimension.SOUL, Layer.PRINCIPLE, "old value", [2], ["Q1"])
    await db.record_question_answered("u1", "QV", 2, "principle")

    reply = await process_turn("u1", "重談 語氣", object(), db, selector, settings)

    assert "封存" in reply
    summary = await db.load_anchors_summary("u1")
    assert summary[Dimension.VOICE] == []
    assert len(summary[Dimension.SOUL]) == 1
    assert await db.load_asked_question_ids("u1") == {"QV"}
