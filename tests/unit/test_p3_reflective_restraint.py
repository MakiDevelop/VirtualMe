"""P3 Reflective Restraint hard gate - Constitution v1.1 §P3."""

from virtualme.interview.guardrail import Guardrail
from virtualme.interview.turn_reasoner_schema import (
    BoundaryStatus,
    EngagementState,
    NextMove,
    TurnReasonerOutput,
)


def _output(**overrides):
    """Build a baseline TurnReasonerOutput for tests."""
    defaults = dict(
        read="test",
        boundary_status=BoundaryStatus.NONE,
        engagement_state=EngagementState.ENGAGED,
        next_move=NextMove.ADVANCE,
        next_question_id="q1",
        should_echo=False,
        echo_content=None,
        reflection_note=None,
        reply="ok",
    )
    defaults.update(overrides)
    return TurnReasonerOutput(**defaults)


def test_explicit_refusal_sets_skip_stop_reason():
    """違規 -> reply 不能解讀; HONOR_SKIP + skip_stop_reason=refusal."""
    g = Guardrail()
    out = g.apply(
        _output(
            boundary_status=BoundaryStatus.EXPLICIT_REFUSAL,
            next_move=NextMove.PROBE,
        ),
        current_probe_count=0,
    )
    assert out.next_move == NextMove.HONOR_SKIP
    assert out.skip_stop_reason == "refusal"


def test_strong_reluctance_with_probe_softens_with_reason():
    g = Guardrail()
    out = g.apply(
        _output(
            boundary_status=BoundaryStatus.STRONG_RELUCTANCE,
            next_move=NextMove.PROBE,
        ),
        current_probe_count=0,
    )
    assert out.next_move == NextMove.SOFTEN
    assert out.skip_stop_reason == "reluctance"


def test_fatigued_state_with_probe_softens_with_reason():
    g = Guardrail()
    out = g.apply(
        _output(
            engagement_state=EngagementState.FATIGUED,
            next_move=NextMove.PROBE,
        ),
        current_probe_count=0,
    )
    assert out.next_move == NextMove.SOFTEN
    assert out.skip_stop_reason == "fatigue"


def test_probe_cap_reached_advances_with_reason():
    g = Guardrail(max_probes_per_question=2)
    out = g.apply(
        _output(next_move=NextMove.PROBE),
        current_probe_count=2,
    )
    assert out.next_move == NextMove.ADVANCE
    assert out.skip_stop_reason == "probe_cap_reached"


def test_no_fork_keeps_default_reason():
    g = Guardrail()
    out = g.apply(
        _output(next_move=NextMove.ADVANCE),
        current_probe_count=0,
    )
    assert out.next_move == NextMove.ADVANCE
    assert out.skip_stop_reason == "none"


def test_reflection_note_not_leaked_into_reply():
    """P3 §M1 bullet 3: reflection_note defaults to internal-only.

    This test confirms Guardrail does not concatenate reflection_note into reply.
    """
    g = Guardrail()
    out = g.apply(
        _output(
            reflection_note="使用者顯示 X 心理 pattern (內部 audit only)",
            reply="好的我們繼續下一題。",
        ),
        current_probe_count=0,
    )
    assert "心理 pattern" not in out.reply
    assert out.reflection_note is not None
