import logging

from anthropic import AsyncAnthropic

from virtualme.config import Settings
from virtualme.export.auto import auto_export_persona
from virtualme.interview import byok
from virtualme.interview.anchor_extractor import extract_anchors
from virtualme.interview.commands import (
    DIMENSION_LABELS,
    RetalkRequest,
    StatusQuery,
    detect_command,
    format_retalk_needs_dimension,
    format_retalk_reply,
    format_status_reply,
)
from virtualme.interview.depth_evaluator import evaluate_depth
from virtualme.interview.follow_up import generate_follow_up, select_rule
from virtualme.interview.models import MODEL_DEEP
from virtualme.interview.pii import scrub_pii
from virtualme.interview.question_selector import QuestionSelector
from virtualme.interview.session_lifecycle import (
    finalize_session_if_closing,
    is_persona_sufficient,
)
from virtualme.storage.db import DB, Dimension, Layer, Question, Session

logger = logging.getLogger(__name__)

DEFAULT_QUESTION = Question(
    id="STATE-OPEN",
    week=1,
    dimension=Dimension.STATE,
    text="How has your work been this past week?",
    energy_tax="low",
)

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
    command = detect_command(incoming_message)
    if command is not None:
        # Meta-commands (status query / re-talk) are handled and replied to
        # without running depth/anchor extraction on the message.
        return await _handle_command(command, interviewee_id, incoming_message, session, db, selector)
    turn_count = await db.count_turns(session.id)
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
    depth = await evaluate_depth(scrub_result.scrubbed_text, current_question.text, active_client)
    await db.record_question_answered(interviewee_id, current_question.id, session.week, depth.value)
    all_anchors = [anchor for anchors in anchors_by_dimension.values() for anchor in anchors]
    rule = select_rule(scrub_result.scrubbed_text, depth, all_anchors)

    # Mine anchors from every answer: the follow-up decision below only changes
    # what the bot asks next, not whether this turn is extracted.
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

    if rule and depth != Layer.PRINCIPLE:
        reply = await generate_follow_up(
            rule, scrub_result.scrubbed_text, current_question.text, active_client
        )
    else:
        next_question = selector.select_next(
            session,
            scrub_result.scrubbed_text,
            anchors_by_dimension,
            energy=5,
            asked_question_ids=asked_question_ids,
            adaptive=settings.adaptive_extraction,
        )
        if next_question is not None:
            await db.set_current_question_id(session.id, next_question.id)
            await db.record_question_asked(interviewee_id, next_question.id, session.week)
        if settings.use_ppa:
            from virtualme.interview.ppa import ppa_response
            from virtualme.interview.reinjection import build_reinjection_anchor, should_reinject

            triples = await db.load_triples(interviewee_id)
            dialogue_context = await _build_context(db, session.id, n_recent=10)
            if should_reinject(turn_count, settings.reinjection_interval):
                anchor = build_reinjection_anchor(interviewee_id, triples[:5])
                dialogue_context = f"{anchor}\n\n{dialogue_context}" if anchor else dialogue_context
            reply = await ppa_response(dialogue_context, triples, active_client, settings)
        else:
            reply = await _final_reply(
                interviewee_id, next_question or DEFAULT_QUESTION, active_client, db
            )

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
    command: StatusQuery | RetalkRequest,
    interviewee_id: str,
    incoming_message: str,
    session: Session,
    db: DB,
    selector: QuestionSelector,
) -> str:
    """Reply to a meta-command. Saves the turn pair but runs no extraction."""
    if isinstance(command, StatusQuery):
        current_question = await _resolve_current_question(
            db, selector, session.id, session.week
        )
        anchors = await db.load_anchors_summary(interviewee_id)
        covered = [dimension for dimension in Dimension if anchors.get(dimension)]
        reply = format_status_reply(current_question.dimension, covered)
    else:
        reply = await _handle_retalk(command, interviewee_id, session, db, selector)

    scrub_result = scrub_pii(incoming_message)
    user_turn = await db.save_turn(session.id, "user", scrub_result.scrubbed_text)
    await db.save_redactions(user_turn.id, scrub_result.redactions)
    await db.save_turn(session.id, "assistant", reply)
    return reply


async def _handle_retalk(
    command: RetalkRequest,
    interviewee_id: str,
    session: Session,
    db: DB,
    selector: QuestionSelector,
) -> str:
    if command.dimension is None:
        return format_retalk_needs_dimension()
    question = _first_question_for_dimension(selector, command.dimension)
    if question is None:
        # No pooled question for that dimension — acknowledge with an open ask.
        label = DIMENSION_LABELS[command.dimension]
        return format_retalk_reply(command.dimension, f"請再多談談關於「{label}」的部分。")
    # Pin the dimension's question so the next answer is attributed to it.
    await db.set_current_question_id(session.id, question.id)
    await db.record_question_asked(interviewee_id, question.id, session.week)
    return format_retalk_reply(command.dimension, question.text)


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
    base = _default_question(selector, week)
    question_id = await db.get_current_question_id(session_id)
    if question_id:
        for question in _all_questions(selector):
            if question.id == question_id:
                base = question
                break
    last_asked = await db.get_last_assistant_content(session_id)
    if last_asked:
        # The previous bot turn is what the current answer actually responds to
        # (a pool question OR a generated follow-up). Keep the pool question id
        # for triangulation; reflect the real wording for depth/anchor context.
        return base.model_copy(update={"text": last_asked})
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
Do not advise, praise, or paraphrase. Preserve exact wording.
Accumulated anchors: {anchors}
Coverage gaps: {gaps}
"""
    response = await claude.messages.create(
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
