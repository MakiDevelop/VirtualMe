from anthropic import AsyncAnthropic

from virtualme.config import Settings
from virtualme.interview.anchor_extractor import extract_anchors
from virtualme.interview.depth_evaluator import evaluate_depth
from virtualme.interview.follow_up import generate_follow_up, select_rule
from virtualme.interview.pii import detect_pii
from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB, Dimension, Layer, Question

DEFAULT_QUESTION = Question(
    id="STATE-OPEN",
    week=1,
    dimension=Dimension.STATE,
    text="How has your work been this past week?",
    energy_tax="low",
)


async def process_turn(
    interviewee_id: str,
    incoming_message: str,
    claude: AsyncAnthropic,
    db: DB,
    selector: QuestionSelector,
    settings: Settings | None = None,
) -> str:
    settings = settings or Settings()
    session = await db.get_or_create_session(interviewee_id, week=1)
    turn_count = await db.count_turns(session.id)
    user_turn = await db.save_turn(session.id, "user", incoming_message)
    pii = detect_pii(incoming_message)
    if pii:
        reply = f"I noticed possible {', '.join(pii)}. Want to switch to a code name?"
        await db.save_turn(session.id, "assistant", reply)
        return reply

    anchors_by_dimension = await db.load_anchors_summary(interviewee_id)
    current_question = _current_question(selector, session.week)
    depth = await evaluate_depth(incoming_message, current_question.text, claude)
    all_anchors = [anchor for anchors in anchors_by_dimension.values() for anchor in anchors]
    rule = select_rule(incoming_message, depth, all_anchors)
    if rule and depth != Layer.PRINCIPLE:
        reply = await generate_follow_up(rule, incoming_message, current_question.text, claude)
    else:
        extracted = await extract_anchors(user_turn, current_question, claude)
        for anchor in extracted:
            await db.save_anchor(
                interviewee_id,
                anchor.dimension,
                anchor.layer,
                anchor.content,
                anchor.source_turn_ids,
            )
        next_question = selector.select_next(session, incoming_message, anchors_by_dimension, energy=5)
        if settings.use_ppa:
            from virtualme.interview.ppa import ppa_response
            from virtualme.interview.reinjection import build_reinjection_anchor, should_reinject

            triples = await db.load_triples(interviewee_id)
            dialogue_context = await _build_context(db, session.id, n_recent=10)
            if should_reinject(turn_count, settings.reinjection_interval):
                anchor = build_reinjection_anchor(interviewee_id, triples[:5])
                dialogue_context = f"{anchor}\n\n{dialogue_context}" if anchor else dialogue_context
            reply = await ppa_response(dialogue_context, triples, claude, settings)
        else:
            reply = await _final_reply(interviewee_id, next_question or DEFAULT_QUESTION, claude, db)

    await db.save_turn(session.id, "assistant", reply)
    return reply


def _current_question(selector: QuestionSelector, week: int) -> Question:
    return (selector.question_pool.get(week) or [DEFAULT_QUESTION])[0]


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
        model="claude-opus-4-7",
        max_tokens=180,
        temperature=0.3,
        system=system,
        messages=[{"role": "user", "content": f"Ask this next: {question.text}"}],
    )
    return response.content[0].text.strip()


async def _build_context(db: DB, session_id: int, n_recent: int = 10) -> str:
    turns = await db.load_recent_turns(session_id, n_recent)
    return "\n".join(f"{turn.role}: {turn.content}" for turn in turns)
