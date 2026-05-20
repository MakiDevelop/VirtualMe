from dataclasses import is_dataclass, replace

from virtualme.interview.turn_reasoner_schema import (
    BoundaryStatus,
    EngagementState,
    NextMove,
    TurnReasonerOutput,
)


def _replace_output(output: TurnReasonerOutput, **changes) -> TurnReasonerOutput:
    if is_dataclass(output):
        return replace(output, **changes)

    data = vars(output).copy()
    data.update(changes)
    return TurnReasonerOutput(**data)


class Guardrail:
    """Conservative guardrail for boundary, fatigue, and probe-budget handling."""

    def __init__(self, max_probes_per_question: int = 2):
        self.max_probes_per_question = max_probes_per_question

    def apply(
        self,
        output: TurnReasonerOutput,
        current_probe_count: int,
    ) -> TurnReasonerOutput:
        new_output = output

        # Explicit refusal has highest priority.
        if output.boundary_status == BoundaryStatus.EXPLICIT_REFUSAL:
            if output.next_move != NextMove.HONOR_SKIP:
                new_output = _replace_output(
                    new_output,
                    next_move=NextMove.HONOR_SKIP,
                    next_question_id=None,
                    skip_stop_reason="refusal",
                )
            return new_output

        if (
            output.boundary_status == BoundaryStatus.STRONG_RELUCTANCE
            and output.next_move == NextMove.PROBE
        ):
            new_output = _replace_output(
                new_output,
                next_move=NextMove.SOFTEN,
                skip_stop_reason="reluctance",
            )

        if (
            output.engagement_state in (EngagementState.FATIGUED, EngagementState.GUARDED)
            and output.next_move == NextMove.PROBE
        ):
            new_output = _replace_output(
                new_output,
                next_move=NextMove.SOFTEN,
                skip_stop_reason="fatigue",
            )

        if (
            current_probe_count >= self.max_probes_per_question
            and output.next_move in (NextMove.PROBE, NextMove.SOFTEN)
        ):
            new_output = _replace_output(
                new_output,
                next_move=NextMove.ADVANCE,
                skip_stop_reason="probe_cap_reached",
            )

        return new_output
