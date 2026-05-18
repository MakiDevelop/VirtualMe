import logging
import unicodedata
from pathlib import Path

from anthropic import AsyncAnthropic

from virtualme.config import Settings
from virtualme.export.auto import auto_export_persona
from virtualme.interview import byok
from virtualme.interview.anchor_extractor import extract_anchors
from virtualme.interview.commands import (
    DIMENSION_LABELS,
    GenerateProfileRequest,
    RestartRequest,
    RetalkRequest,
    RevokeKeyRequest,
    StatusQuery,
    detect_command,
    format_generate_profile_denied,
    format_generate_profile_reply,
    format_restart_reply,
    format_retalk_needs_dimension,
    format_retalk_reply,
    format_revoke_key_reply,
    format_status_reply,
)
from virtualme.interview.depth_evaluator import TurnKind, evaluate_depth
from virtualme.interview.follow_up import generate_follow_up, select_rule
from virtualme.interview.lang import INTERVIEW_OUTPUT_LANGUAGE
from virtualme.interview.models import MODEL_DEEP, create_message
from virtualme.interview.pii import scrub_pii
from virtualme.interview.question_selector import QuestionSelector
from virtualme.interview.session_lifecycle import (
    finalize_session_if_closing,
    is_persona_sufficient,
    is_session_closing,
)
from virtualme.snapshot.core import export_snapshot
from virtualme.storage.db import DB, Dimension, Question, Session
from virtualme.subject import score_completeness

logger = logging.getLogger(__name__)

DEFAULT_QUESTION = Question(
    id="STATE-OPEN",
    week=1,
    dimension=Dimension.STATE,
    text="How has your work been this past week?",
    energy_tax="low",
)
MAX_PROBES_PER_QUESTION = 2

INTERVIEW_ERROR_REPLY = (
    "抱歉，我這邊剛才出了點狀況，麻煩你再說一次。"  # noqa: RUF001
    " (Sorry, something went wrong on my side — please try again.)"
)


async def process_turn(
    interviewee_id: str,
    incoming_message: str,
    claude: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
    settings: Settings | None = None,
    override_week: int | None = None,
) -> str:
    settings = settings or Settings()
    active_client = claude
    pre_gate_command = detect_command(incoming_message)
    if isinstance(pre_gate_command, RevokeKeyRequest):
        # Revocation is allowed before consent/BYOK so users can always remove
        # a stored key without first accepting more data processing terms.
        return _handle_revoke_key(interviewee_id, settings)
    if settings.consent_required:
        consent_reply = byok.run_consent_gate(
            interviewee_id,
            incoming_message,
            settings.byok_keys_dir,
        )
        if consent_reply is not None:
            return consent_reply
    if settings.byok_enabled:
        # BYOK gate runs before session/scrub/save_turn/any LLM call.
        gate = await byok.run_byok_gate(interviewee_id, incoming_message, settings.byok_keys_dir)
        if gate.reply is not None:
            return gate.reply
        # Interview LLM calls run on the interviewee's own key.
        assert gate.api_key is not None
        active_client = byok.build_client(gate.api_key)
    max_week = (
        settings.max_extraction_rounds
        if settings.adaptive_extraction
        else max(selector.question_pool)
        if selector.question_pool
        else DEFAULT_QUESTION.week
    )
    week = (
        max(1, min(override_week, max_week))
        if override_week is not None
        else await db.get_current_week(interviewee_id, max_week)
    )
    session = await db.get_or_create_session(interviewee_id, week=week)
    command = pre_gate_command
    if is_session_closing(incoming_message):
        return await _close_session(
            interviewee_id,
            incoming_message,
            active_client,
            db,
            session,
            settings,
            max_week,
        )
    if command is not None:
        # Meta-commands (status query / re-talk) are handled and replied to
        # without running depth/anchor extraction on the message.
        return await _handle_command(
            command,
            interviewee_id,
            incoming_message,
            session,
            active_client,
            db,
            selector,
            settings,
        )
    turn_count = await db.count_turns(session.id)
    if _is_light_greeting(incoming_message):
        return await _handle_light_greeting(
            interviewee_id,
            incoming_message,
            session,
            active_client,
            db,
            selector,
        )

    scrub_result = scrub_pii(incoming_message)
    if scrub_result.redactions:
        logger.info(
            "PII redacted: %s items in turn from %s",
            len(scrub_result.redactions),
            interviewee_id,
        )
    user_turn = await db.save_turn(session.id, "user", scrub_result.scrubbed_text)
    await db.save_redactions(user_turn.id, scrub_result.redactions)

    anchors_by_dimension = await db.load_anchors_summary(interviewee_id)
    asked_question_ids = await db.load_asked_question_ids(interviewee_id)
    current_question = await _resolve_current_question(db, selector, session.id, session.week)
    assessment = await evaluate_depth(
        scrub_result.scrubbed_text, current_question.text, active_client
    )
    if assessment.parse_failed:
        reply = await _restate_current_question(
            interviewee_id, current_question, active_client, db
        )
        await db.save_turn(session.id, "assistant", reply)
        return reply
    if assessment.kind == TurnKind.META:
        reply = await _handle_non_answer(
            interviewee_id,
            scrub_result.scrubbed_text,
            current_question,
            session,
            selector,
            settings,
            active_client,
            db,
            is_meta=True,
            anchors_by_dimension=anchors_by_dimension,
            asked_question_ids=asked_question_ids,
        )
        await db.save_turn(session.id, "assistant", reply)
        return reply
    if assessment.kind == TurnKind.EVASION:
        reply = await _handle_non_answer(
            interviewee_id,
            scrub_result.scrubbed_text,
            current_question,
            session,
            selector,
            settings,
            active_client,
            db,
            is_meta=False,
            anchors_by_dimension=anchors_by_dimension,
            asked_question_ids=asked_question_ids,
        )
        await db.save_turn(session.id, "assistant", reply)
        return reply

    depth = assessment.depth
    await db.record_question_answered(interviewee_id, current_question.id, session.week, depth.value)
    all_anchors = [anchor for anchors in anchors_by_dimension.values() for anchor in anchors]
    rule = select_rule(scrub_result.scrubbed_text, depth, all_anchors)

    if assessment.kind == TurnKind.SUFFICIENT:
        extracted_anchors = await extract_anchors(user_turn, current_question, active_client)
        for anchor in extracted_anchors:
            await db.save_anchor(
                interviewee_id,
                anchor.dimension,
                anchor.layer,
                anchor.content,
                anchor.source_turn_ids,
                anchor.source_question_ids,
            )

    probe_count = await db.get_probe_count(interviewee_id, current_question.id)
    should_probe = (
        assessment.needs_follow_up
        and rule is not None
        and probe_count < MAX_PROBES_PER_QUESTION
    )
    if should_probe:
        await db.record_question_probe(interviewee_id, current_question.id, session.week)
        reply = await generate_follow_up(
            rule, scrub_result.scrubbed_text, current_question.text, active_client
        )
    else:
        excluded = {current_question.id} if probe_count >= MAX_PROBES_PER_QUESTION else set()
        next_question = selector.select_next(
            session,
            scrub_result.scrubbed_text,
            anchors_by_dimension,
            energy=5,
            asked_question_ids=asked_question_ids,
            excluded_question_ids=excluded,
            adaptive=settings.adaptive_extraction,
        )
        if next_question is not None:
            await db.set_current_question_id(session.id, next_question.id)
            await db.record_question_asked(interviewee_id, next_question.id, session.week)
        if next_question is not None:
            reply = await _final_reply(interviewee_id, next_question, active_client, db)
        elif settings.use_ppa:
            from virtualme.interview.ppa import ppa_response
            from virtualme.interview.reinjection import build_reinjection_anchor, should_reinject

            triples = await db.load_triples(interviewee_id)
            dialogue_context = await _build_context(db, session.id, n_recent=10)
            if should_reinject(turn_count, settings.reinjection_interval):
                anchor = build_reinjection_anchor(interviewee_id, triples[:5])
                dialogue_context = f"{anchor}\n\n{dialogue_context}" if anchor else dialogue_context
            reply = await ppa_response(dialogue_context, triples, active_client, settings)
        else:
            reply = await _final_reply(interviewee_id, DEFAULT_QUESTION, active_client, db)

    await db.save_turn(session.id, "assistant", reply)
    turns_so_far = await db.load_session_turns(session.id)
    extracted = await finalize_session_if_closing(
        session_id=session.id,
        interviewee_id=interviewee_id,
        user_text=incoming_message,
        turns=turns_so_far,
        claude=active_client,
        db=db,
    )
    if extracted:
        logger.info("Session %s closed: extracted %s triples", session.id, extracted)
        await _auto_export_if_sufficient(
            db, interviewee_id, session.week, max_week, settings
        )
    return reply


async def _close_session(
    interviewee_id: str,
    incoming_message: str,
    active_client: AsyncAnthropic,
    db: DB,
    session: Session,
    settings: Settings,
    max_week: int,
) -> str:
    scrub_result = scrub_pii(incoming_message)
    if scrub_result.redactions:
        logger.info(
            "PII redacted: %s items in closing turn from %s",
            len(scrub_result.redactions),
            interviewee_id,
        )
    user_turn = await db.save_turn(session.id, "user", scrub_result.scrubbed_text)
    await db.save_redactions(user_turn.id, scrub_result.redactions)
    reply = "好，今天先到這裡。我會把這段先整理起來。"  # noqa: RUF001
    await db.save_turn(session.id, "assistant", reply)
    turns_so_far = await db.load_session_turns(session.id)
    extracted = await finalize_session_if_closing(
        session_id=session.id,
        interviewee_id=interviewee_id,
        user_text=incoming_message,
        turns=turns_so_far,
        claude=active_client,
        db=db,
    )
    if extracted:
        logger.info("Session %s closed: extracted %s triples", session.id, extracted)
        await _auto_export_if_sufficient(
            db, interviewee_id, session.week, max_week, settings
        )
    return reply


async def _handle_non_answer(
    interviewee_id: str,
    user_text: str,
    current_question: Question,
    session: Session,
    selector: QuestionSelector,
    settings: Settings,
    active_client: AsyncAnthropic,
    db: DB,
    *,
    is_meta: bool,
    anchors_by_dimension: dict,
    asked_question_ids: set[str],
) -> str:
    count = await db.record_question_non_answer(
        interviewee_id, current_question.id, session.week
    )
    if not is_meta:
        return _pause_current_question()
    if count < 2:
        return await _bridge_to_current_question(
            interviewee_id, user_text, current_question, active_client, db
        )

    next_question = selector.select_next(
        session,
        user_text,
        anchors_by_dimension,
        energy=5,
        asked_question_ids=asked_question_ids,
        adaptive=settings.adaptive_extraction,
    )
    await db.reset_question_non_answer(interviewee_id, current_question.id)
    if next_question is None:
        return await _bridge_to_current_question(
            interviewee_id, user_text, current_question, active_client, db
        )

    await db.set_current_question_id(session.id, next_question.id)
    await db.record_question_asked(interviewee_id, next_question.id, session.week)
    return await _final_reply(interviewee_id, next_question, active_client, db)


async def _restate_current_question(
    interviewee_id: str, question: Question, claude: AsyncAnthropic, db: DB
) -> str:
    # Re-ask via _final_reply so the question is rendered in Traditional Chinese
    # — the English question-pool text must never reach the interviewee.
    asked = await _final_reply(interviewee_id, question, claude, db)
    return f"我們先回到剛才這題。\n{asked}"


async def _bridge_to_current_question(
    interviewee_id: str, user_text: str, question: Question, claude: AsyncAnthropic, db: DB
) -> str:
    if _asks_for_traditional_chinese(user_text):
        prefix = "可以，我們用繁體中文。"  # noqa: RUF001
    else:
        prefix = "可以，我先記下這點。"  # noqa: RUF001
    asked = await _final_reply(interviewee_id, question, claude, db)
    return f"{prefix}我們回到剛才這題。\n{asked}"


def _pause_current_question() -> str:
    return (
        "好, 這題我們先停在這裡。"
        "如果你想換題、休息一下, 或指定要談哪一塊, 直接跟我說。"
    )


def _asks_for_traditional_chinese(text: str) -> bool:
    lowered = text.lower()
    markers = ("中文", "繁體", "繁中", "traditional chinese", "taiwan")
    return any(marker in lowered for marker in markers)


def _is_light_greeting(text: str) -> bool:
    stripped = _strip_trailing_marks(text.strip().lower())
    greetings = {
        "hi",
        "hello",
        "hey",
        "哈囉",
        "哈啰",
        "嗨",
        "你好",
        "您好",
        "早安",
        "午安",
        "晚安",
    }
    return stripped in greetings


def _strip_trailing_marks(text: str) -> str:
    while text and unicodedata.category(text[-1])[0] in {"P", "S"}:
        text = text[:-1].rstrip()
    return text


async def _handle_light_greeting(
    interviewee_id: str,
    incoming_message: str,
    session: Session,
    active_client: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
) -> str:
    """Resume from known progress instead of classifying a greeting as an answer."""
    scrub_result = scrub_pii(incoming_message)
    user_turn = await db.save_turn(session.id, "user", scrub_result.scrubbed_text)
    await db.save_redactions(user_turn.id, scrub_result.redactions)

    question = await _current_pool_question(db, selector, session.id, session.week)
    if await db.get_current_question_id(session.id) is None:
        await db.set_current_question_id(session.id, question.id)
        await db.record_question_asked(interviewee_id, question.id, session.week)

    anchors = await db.load_anchors_summary(interviewee_id)
    completeness = score_completeness(anchors)
    progress_prefix = _progress_resume_prefix(completeness.total_score)
    last_asked = await db.get_last_assistant_content(session.id)
    if last_asked:
        is_restart_resume = _is_restart_reply(last_asked)
        last_asked = _clean_resume_question(last_asked)
        if is_restart_resume or _has_unresolved_placeholder(last_asked):
            rendered_question = await _final_reply(interviewee_id, question, active_client, db)
            reply = (
                f"{progress_prefix}\n"
                f"我們從【{DIMENSION_LABELS[question.dimension]}】開始。\n"
                f"{rendered_question}"
            )
        else:
            reply = (
                f"{progress_prefix}\n"
                f"我們目前在【{DIMENSION_LABELS[question.dimension]}】這一塊。\n"
                f"剛才問的是:\n{last_asked}"
            )
    else:
        rendered_question = await _final_reply(interviewee_id, question, active_client, db)
        reply = (
            f"{progress_prefix}\n"
            f"我們從【{DIMENSION_LABELS[question.dimension]}】開始。\n"
            f"{rendered_question}"
        )
    await db.save_turn(session.id, "assistant", reply)
    return reply


def _clean_resume_question(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("好, 我會從頭開始萃取。"):
        lines = cleaned.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("封存摘要:"):
                return "\n".join(lines[index + 1 :]).strip()
        return lines[-1].strip() if lines else cleaned
    if "我先記下這點" in cleaned and "我們回到剛才這題" in cleaned:
        return cleaned.split("\n", 1)[-1].strip()
    if cleaned.startswith("我們先回到剛才這題。"):
        return cleaned.split("\n", 1)[-1].strip()
    return cleaned


def _is_restart_reply(content: str) -> bool:
    return content.strip().startswith("好, 我會從頭開始萃取。")


def _has_unresolved_placeholder(content: str) -> bool:
    return "{" in content or "}" in content


def _progress_resume_prefix(total_score: float) -> str:
    if total_score >= 85:
        return "嗨, 你已經快完成了, 我們再收一點關鍵細節就好。"
    if total_score >= 45:
        return "嗨, 我們已經完成一大段了。你現在方便繼續嗎?"
    return "嗨, 我們才剛開始, 我會慢慢來, 一次只問一題。"


async def _auto_export_if_sufficient(
    db: DB,
    interviewee_id: str,
    round_number: int,
    max_rounds: int,
    settings: Settings,
) -> None:
    """Export the 8-dimension persona archive — but only once extraction is
    judged sufficient. An incomplete interview leaves its anchors staged in the
    DB; nothing is written to disk until `is_persona_sufficient` is met.
    """
    if not settings.persona_auto_export:
        return
    anchors = await db.load_anchors_summary(interviewee_id)
    if not is_persona_sufficient(round_number, max_rounds, anchors):
        logger.info(
            "Persona extraction for %s not yet sufficient; archive staged in DB, not exported",
            interviewee_id,
        )
        return
    try:
        paths = await auto_export_persona(db, interviewee_id, settings.persona_export_dir)
        logger.info("Persona archive exported for %s: %s files", interviewee_id, len(paths))
    except Exception as exc:
        logger.error("Persona auto-export failed for %s: %s", interviewee_id, exc)


async def _handle_command(
    command: StatusQuery | RetalkRequest | RestartRequest | GenerateProfileRequest | RevokeKeyRequest,
    interviewee_id: str,
    incoming_message: str,
    session: Session,
    active_client: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
    settings: Settings,
) -> str:
    """Reply to a meta-command. Saves the turn pair but runs no extraction."""
    if isinstance(command, GenerateProfileRequest):
        scrub_result = scrub_pii(incoming_message)
        user_turn = await db.save_turn(session.id, "user", scrub_result.scrubbed_text)
        await db.save_redactions(user_turn.id, scrub_result.redactions)
        reply = await _handle_generate_profile(interviewee_id, db, settings)
        await db.save_turn(session.id, "assistant", reply)
        return reply

    if isinstance(command, RevokeKeyRequest):
        scrub_result = scrub_pii(incoming_message)
        user_turn = await db.save_turn(session.id, "user", scrub_result.scrubbed_text)
        await db.save_redactions(user_turn.id, scrub_result.redactions)
        reply = _handle_revoke_key(interviewee_id, settings)
        await db.save_turn(session.id, "assistant", reply)
        return reply

    if isinstance(command, RestartRequest):
        scrub_result = scrub_pii(incoming_message)
        user_turn = await db.save_turn(session.id, "user", scrub_result.scrubbed_text)
        await db.save_redactions(user_turn.id, scrub_result.redactions)
        reply, new_session = await _handle_restart(
            interviewee_id, active_client, db, selector, settings
        )
        await db.save_turn(new_session.id, "assistant", reply)
        return reply

    if isinstance(command, StatusQuery):
        current_question = await _resolve_current_question(
            db, selector, session.id, session.week
        )
        anchors = await db.load_anchors_summary(interviewee_id)
        covered = [dimension for dimension in Dimension if anchors.get(dimension)]
        reply = format_status_reply(
            current_question.dimension,
            covered,
            score_completeness(anchors),
        )
    else:
        reply = await _handle_retalk(command, interviewee_id, session, db, selector)

    scrub_result = scrub_pii(incoming_message)
    user_turn = await db.save_turn(session.id, "user", scrub_result.scrubbed_text)
    await db.save_redactions(user_turn.id, scrub_result.redactions)
    await db.save_turn(session.id, "assistant", reply)
    return reply


async def _handle_generate_profile(
    interviewee_id: str,
    db: DB,
    settings: Settings,
) -> str:
    if not _line_snapshot_export_allowed(interviewee_id, settings):
        return format_generate_profile_denied()
    try:
        paths = await export_snapshot(db, interviewee_id, Path(settings.snapshot_export_dir))
    except Exception as exc:
        logger.exception("Snapshot export failed for %s: %s", interviewee_id, exc)
        return "行為模式檔草稿輸出失敗; 資料仍保留在訪談資料庫, 請稍後再試。"
    return format_generate_profile_reply(sorted(path.name for path in paths))


def _line_snapshot_export_allowed(interviewee_id: str, settings: Settings) -> bool:
    if not settings.line_snapshot_export_enabled:
        return False
    allowed = {
        item.strip()
        for item in settings.line_snapshot_export_user_ids.split(",")
        if item.strip()
    }
    if settings.owner_line_user_id:
        allowed.add(settings.owner_line_user_id)
    return interviewee_id in allowed


def _handle_revoke_key(interviewee_id: str, settings: Settings) -> str:
    removed = byok.delete_key(settings.byok_keys_dir, interviewee_id)
    return format_revoke_key_reply(removed)


async def _handle_restart(
    interviewee_id: str,
    active_client: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
    settings: Settings,
) -> tuple[str, Session]:
    archive_note = "已先輸出目前的 markdown archive 快照。"
    try:
        paths = await auto_export_persona(db, interviewee_id, settings.persona_export_dir)
        archive_note = f"已先輸出目前的 markdown archive 快照: {len(paths)} files。"
    except Exception as exc:
        logger.error("Restart archive export failed for %s: %s", interviewee_id, exc)
        archive_note = "markdown archive 快照輸出失敗; DB 內仍會保留封存資料。"

    archived_counts = await db.restart_interview(interviewee_id)
    new_session = await db.get_or_create_session(interviewee_id, week=1)
    first_question = _default_question(selector, 1)
    await db.set_current_question_id(new_session.id, first_question.id)
    await db.record_question_asked(interviewee_id, first_question.id, 1)
    rendered_question = await _final_reply(interviewee_id, first_question, active_client, db)
    return format_restart_reply(archive_note, archived_counts, rendered_question), new_session


async def _handle_retalk(
    command: RetalkRequest,
    interviewee_id: str,
    session: Session,
    db: DB,
    selector: QuestionSelector,
) -> str:
    if command.dimension is None:
        return format_retalk_needs_dimension()
    question_ids = [
        question.id for question in _all_questions(selector) if question.dimension == command.dimension
    ]
    archived_count = await db.restart_dimension(
        interviewee_id,
        command.dimension,
        question_ids,
    )
    question = _first_question_for_dimension(selector, command.dimension)
    if question is None:
        # No pooled question for that dimension — acknowledge with an open ask.
        label = DIMENSION_LABELS[command.dimension]
        return format_retalk_reply(
            command.dimension,
            f"我已先封存這一塊既有的 {archived_count} 條記憶。"
            f"請重新從零談談關於「{label}」的部分。",
        )
    # Pin the dimension's question so the next answer is attributed to it.
    await db.set_current_question_id(session.id, question.id)
    await db.record_question_asked(interviewee_id, question.id, session.week)
    return format_retalk_reply(
        command.dimension,
        f"我已先封存這一塊既有的 {archived_count} 條記憶, 接下來從零重談。\n{question.text}",
    )


def _first_question_for_dimension(
    selector: QuestionSelector, dimension: Dimension
) -> Question | None:
    for question in _all_questions(selector):
        if question.dimension == dimension:
            return question
    return None


async def _resolve_current_question(
    db: DB, selector: QuestionSelector, session_id: int, week: int
) -> Question:
    base = await _current_pool_question(db, selector, session_id, week)
    last_asked = await db.get_last_assistant_content(session_id)
    if last_asked:
        # The previous bot turn is what the current answer actually responds to
        # (a pool question OR a generated follow-up). Keep the pool question id
        # for triangulation; reflect the real wording for depth/anchor context.
        return base.model_copy(update={"text": last_asked})
    return base


async def _current_pool_question(
    db: DB, selector: QuestionSelector, session_id: int, week: int
) -> Question:
    base = _default_question(selector, week)
    question_id = await db.get_current_question_id(session_id)
    if question_id:
        for question in _all_questions(selector):
            if question.id == question_id:
                return question
    return base


def _default_question(selector: QuestionSelector, week: int) -> Question:
    return (selector.question_pool.get(week) or [DEFAULT_QUESTION])[0]


def _all_questions(selector: QuestionSelector) -> list[Question]:
    return [question for questions in selector.question_pool.values() for question in questions]


async def _final_reply(
    interviewee_id: str, question: Question, claude: AsyncAnthropic, db: DB
) -> str:
    anchors = await db.load_anchors_summary(interviewee_id)
    gaps = await db.compute_coverage_gap(interviewee_id)
    system = f"""
You are the interview assistant for {interviewee_id}. Ask one question at a time.
{INTERVIEW_OUTPUT_LANGUAGE}
Translate the source question into natural Traditional Chinese, preserving its
exact meaning, depth, and directness. Do not advise, praise, soften, or add commentary.
Accumulated anchors: {anchors}
Coverage gaps: {gaps}
"""
    response = await create_message(
        claude,
        model=MODEL_DEEP,
        max_tokens=180,
        temperature=0.3,
        system=system,
        messages=[{"role": "user", "content": f"Ask this next: {question.text}"}],
    )
    return response.content[0].text.strip()


async def _build_context(db: DB, session_id: int, n_recent: int = 10) -> str:
    turns = await db.load_recent_turns(session_id, n_recent)
    return "\n".join(f"{turn.role}: {turn.content}" for turn in turns)
