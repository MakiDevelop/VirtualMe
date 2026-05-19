from dataclasses import replace
from virtualme.interview.turn_reasoner_schema import (
    TurnReasonerOutput,
    BoundaryStatus,
    NextMove,
    EngagementState,
)


class Guardrail:
    """
    保守型 Guardrail（加強版 v3）
    - explicit_refusal 最高優先，強制 honor_skip
    - strong_reluctance 處理強度高於 fatigued/guarded
    - fatigued / guarded 優先使用 soften
    - 只有在明確不適合時才清掉 next_question_id
    """

    def __init__(self, max_probes_per_question: int = 2):
        self.max_probes_per_question = max_probes_per_question

    def apply(
        self,
        output: TurnReasonerOutput,
        current_probe_count: int,
    ) -> TurnReasonerOutput:
        new_output = output

        # 1. 最高優先：明確拒絕 → 強制 honor_skip 並清掉題目
        if output.boundary_status == BoundaryStatus.EXPLICIT_REFUSAL:
            if output.next_move != NextMove.HONOR_SKIP:
                new_output = replace(
                    new_output,
                    next_move=NextMove.HONOR_SKIP,
                    next_question_id=None,
                )
            return new_output   # 明確拒絕直接返回，不再往下判斷

        # 2. strong_reluctance：比 fatigued/guarded 更保守
        if output.boundary_status == BoundaryStatus.STRONG_RELUCTANCE:
            if output.next_move == NextMove.PROBE:
                new_output = replace(new_output, next_move=NextMove.SOFTEN)

        # 3. fatigued / guarded：優先使用 soften 降低壓力
        if output.engagement_state in (EngagementState.FATIGUED, EngagementState.GUARDED):
            if output.next_move == NextMove.PROBE:
                new_output = replace(new_output, next_move=NextMove.SOFTEN)

        # 4. probe 上限硬底線
        if current_probe_count >= self.max_probes_per_question:
            if output.next_move in (NextMove.PROBE, NextMove.SOFTEN):
                new_output = replace(new_output, next_move=NextMove.ADVANCE)

        return new_output
