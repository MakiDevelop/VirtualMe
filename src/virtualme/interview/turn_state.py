"""TurnState (L1): read-only snapshot of per-turn interview context.

Purpose: feed a single, well-fed context object to the future turn_reasoner (L2).
Assembled purely from existing DB helpers + QuestionSelector. No decision logic,
no side effects, no changes to process_turn or any existing call sites.

Design constraints (per 2026-05-18 ratified slice):
- GREEN: new file only; zero behavior change until L4 flag wiring.
- Supports restart / retalk / light-greeting / normal paths.
- Goal: subject.goal (if set) else explicit DEFAULT_GOAL for M1.
- Current question keeps pool identity (id/dim); last_prompt_text reflects
  what the user is actually replying to (may be follow-up wording).
- candidate_questions = not-yet-asked questions in the relevant pool
  (week-specific or adaptive). L2 can further shortlist 2-3 from this.

Resolution helpers are intentionally duplicated (tiny, deterministic) to keep
turn_state.py self-contained in L1. Will be consolidated when wiring in L4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from virtualme.interview.question_selector import QuestionSelector
from virtualme.storage.db import DB, Anchor, Dimension, Layer, Question, Session, Turn

# Fallback goal for M1 slice (explicit, matches the "會推理、不像機器人" objective).
# Real per-subject goal (if populated via future UI or init) takes precedence.
DEFAULT_GOAL: str = (
    "Extract rich, layered (fact/pattern/principle) evidence across 8 dimensions "
    "(SOUL, VOICE, SKILL, PEOPLE, HISTORY, JOURNAL, BOUNDARIES, STATE) "
    "to build a truthful, non-overfitted persona profile of the interviewee."
)

# Safe fallback when selector has no questions at all (should never happen in prod).
# Mirrors bot.DEFAULT_QUESTION but defined locally to avoid early import coupling.
_FALLBACK_QUESTION = Question(
    id="STATE-OPEN",
    week=1,
    dimension=Dimension.STATE,
    text="How has your work been this past week?",
    energy_tax="low",
)


# === Layered Coverage Model (for real 8維 × 3層 progress) ===

@dataclass
class LayerProgress:
    """Progress for one layer of one dimension."""
    evidence_count: int = 0
    quality_score: float = 0.0      # 0.0 ~ 1.0
    status: str = "none"            # "none" | "partial" | "sufficient"


@dataclass
class DimensionProgress:
    """Progress across three layers for one dimension."""
    dimension: Dimension
    layers: dict[Layer, LayerProgress] = field(default_factory=dict)
    overall_reached: Layer | None = None   # highest layer that reached "sufficient"


@dataclass
class CoverageSnapshot:
    """Complete snapshot of collection progress for all 8 dimensions."""
    per_dimension: dict[Dimension, DimensionProgress] = field(default_factory=dict)
    overall_completion: float = 0.0        # rough 0.0~1.0 across all relevant layers


class TurnState(BaseModel):
    """Immutable (frozen) snapshot of everything the reasoner needs for one turn.

    All fields are read-only after construction. Use .model_copy() only for
    test scaffolding; never mutate in production paths.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    goal: str
    """整場訪談的目標 (不隨單題漂移)。"""

    current_question: Question
    """當前題的池定義 (id, week, dimension, 原始 text)。id 用於記錄與 anchor 歸屬。"""

    last_prompt_text: str | None = None
    """實際送給受訪者的上一個 bot 訊息文字 (可能是追問改寫或翻譯後版本)。
    若 None, 代表這是新 session 或 resume 後第一題。"""

    recent_history: list[Turn] = []
    """最近 N 輪對話 (chronological)。role + content, 供承接前文。"""

    anchors_summary: dict[Dimension, list[Anchor]] = {}
    """已萃取 anchor 摘要 (per dimension), 供 coverage 與 gap 判斷。"""

    coverage_gaps: dict[Dimension, float] = {}
    """Coverage gap 0~1 (值越高越缺)。由 anchors 動態計算。"""

    coverage_snapshot: CoverageSnapshot = CoverageSnapshot()
    """Real per-dimension per-layer progress (L2/L3)."""

    probe_count: int = 0
    """本題已追問次數 (硬 cap 由 L3 護欄管)。"""

    candidate_questions: list[Question] = []
    """本輪可選的候選題清單 (尚未 asked_count > 0 的 pool 問題)。
    L2 reasoner 從中挑 (或再短列 2-3 題)。"""


async def build_turn_state(
    interviewee_id: str,
    db: DB,
    selector: QuestionSelector,
    session: Session,
    adaptive: bool = False,
) -> TurnState:
    """Assemble a frozen TurnState for the current moment of this interviewee/session.

    Safe for all entry points:
    - Normal answer path (after resolve_current)
    - Light greeting / resume
    - Post-restart (new week-1 session, first question, probe=0)
    - Post-retalk (dimension reset, current pinned to first of that dim)

    Does NOT call any setter (record_*, set_current_*, save_*). Pure read + derive.
    """
    subject = await db.get_or_create_subject(interviewee_id)
    goal = subject.goal or DEFAULT_GOAL

    current_q = await _resolve_current_question(db, selector, session.id, session.week)
    last_prompt_text = await db.get_last_assistant_content(session.id)
    recent_history = await db.load_recent_turns(session.id, 10)
    anchors_summary = await db.load_anchors_summary(interviewee_id)
    coverage_gaps = await db.compute_coverage_gap(interviewee_id)
    probe_count = await db.get_probe_count(interviewee_id, current_q.id)

    # === Compute real Layered Coverage (first version) ===
    coverage_snapshot = _compute_coverage_snapshot(anchors_summary)

    asked = await db.load_asked_question_ids(interviewee_id)

    # Relevant pool for candidates (same policy as selector.select_next)
    if adaptive:
        pool = [q for questions in selector.question_pool.values() for q in questions]
    else:
        pool = selector.question_pool.get(session.week, []) or [
            q for questions in selector.question_pool.values() for q in questions
        ]

    # Not-yet-asked first; if everything asked (edge), fall back to full pool for this context
    candidate_questions: list[Question] = [q for q in pool if q.id not in asked] or pool

    return TurnState(
        goal=goal,
        current_question=current_q,
        last_prompt_text=last_prompt_text,
        recent_history=recent_history,
        anchors_summary=anchors_summary,
        coverage_gaps=coverage_gaps,
        coverage_snapshot=coverage_snapshot,
        probe_count=probe_count,
        candidate_questions=candidate_questions,
    )


# ----------------------------------------------------------------------------
# Internal resolution helpers (L1 isolation)
# Exact mirrors of bot._current_pool_question / _resolve... / _all... / _default...
# Consolidated into a shared helper module at L4 wiring time.
# ----------------------------------------------------------------------------


async def _resolve_current_question(
    db: DB, selector: QuestionSelector, session_id: int, week: int
) -> Question:
    """Return the Question the current user message is answering.

    - id / dimension / week come from the pool question (stable for storage).
    - text may be overridden by the actual last assistant utterance (follow-up
      wording or natural-language render) so depth/anchor context is accurate.
    """
    base = await _current_pool_question(db, selector, session_id, week)
    last_asked = await db.get_last_assistant_content(session_id)
    if last_asked:
        return base.model_copy(update={"text": last_asked})
    return base


async def _current_pool_question(
    db: DB, selector: QuestionSelector, session_id: int, week: int
) -> Question:
    """The canonical pool question for this session/week (or default)."""
    base = _default_question(selector, week)
    question_id = await db.get_current_question_id(session_id)
    if question_id:
        for question in _all_questions(selector):
            if question.id == question_id:
                return question
    return base


def _default_question(selector: QuestionSelector, week: int) -> Question:
    """First question of the week, or the absolute fallback."""
    questions = selector.question_pool.get(week)
    if questions:
        return questions[0]
    # absolute last resort (matches bot.DEFAULT_QUESTION semantics)
    return _FALLBACK_QUESTION


def _all_questions(selector: QuestionSelector) -> list[Question]:
    """Flatten the entire pool (used for lookup by id)."""
    return [question for questions in selector.question_pool.values() for question in questions]


# === Real Coverage Computation (L2 first version) ===

def _compute_coverage_snapshot(
    anchors_summary: dict[Dimension, list[Anchor]],
) -> CoverageSnapshot:
    """First-pass real computation of per-dimension per-layer progress.

    This is intentionally simple for L2. Quality scoring can be made much
    smarter in L3 (triangulation, recency, contradiction, source diversity, etc.).
    """
    snapshot = CoverageSnapshot()
    total_score_sum = 0.0
    dim_count = 0

    for dim in list(Dimension):
        dim_prog = DimensionProgress(dimension=dim)
        dim_prog.layers = {layer: LayerProgress() for layer in Layer}

        anchors = anchors_summary.get(dim, []) if anchors_summary else []

        layer_counts: dict[Layer, int] = {layer: 0 for layer in Layer}
        for anchor in anchors:
            if hasattr(anchor, "layer") and anchor.layer in layer_counts:
                layer_counts[anchor.layer] += 1

        # Simple scoring: ~0.25 per anchor, capped
        for layer, count in layer_counts.items():
            score = min(1.0, count * 0.28)
            status = "none"
            if score >= 0.75:
                status = "sufficient"
            elif score >= 0.35:
                status = "partial"

            dim_prog.layers[layer] = LayerProgress(
                evidence_count=count,
                quality_score=score,
                status=status,
            )

            # Track highest layer reached at "sufficient"
            if status == "sufficient":
                if dim_prog.overall_reached is None:
                    dim_prog.overall_reached = layer
                else:
                    # Real Layer order: FACT < PATTERN < PRINCIPLE
                    order = [Layer.FACT, Layer.PATTERN, Layer.PRINCIPLE]
                    if order.index(layer) > order.index(dim_prog.overall_reached):
                        dim_prog.overall_reached = layer

        # Rough dimension contribution (PATTERN weighted more)
        dim_score = (
            dim_prog.layers[Layer.FACT].quality_score * 0.2 +
            dim_prog.layers[Layer.PATTERN].quality_score * 0.6 +
            dim_prog.layers[Layer.PRINCIPLE].quality_score * 0.2
        )

        snapshot.per_dimension[dim] = dim_prog
        total_score_sum += dim_score
        dim_count += 1

    if dim_count > 0:
        snapshot.overall_completion = round(total_score_sum / dim_count, 2)

    return snapshot
