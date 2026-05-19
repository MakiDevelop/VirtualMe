from dataclasses import replace

from virtualme.interview.turn_reasoner_schema import (
    BoundaryStatus,
    EngagementState,
    NextMove,
    TurnReasonerOutput,
)


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
                new_output = replace(
                    new_output,
                    next_move=NextMove.HONOR_SKIP,
                    next_question_id=None,
                )
            return new_output

        if (
            output.boundary_status == BoundaryStatus.STRONG_RELUCTANCE
            and output.next_move == NextMove.PROBE
        ):
            new_output = replace(new_output, next_move=NextMove.SOFTEN)

        if (
            output.engagement_state in (EngagementState.FATIGUED, EngagementState.GUARDED)
            and output.next_move == NextMove.PROBE
        ):
            new_output = replace(new_output, next_move=NextMove.SOFTEN)

        if (
            current_probe_count >= self.max_probes_per_question
            and output.next_move in (NextMove.PROBE, NextMove.SOFTEN)
        ):
            new_output = replace(new_output, next_move=NextMove.ADVANCE)

        return new_output
