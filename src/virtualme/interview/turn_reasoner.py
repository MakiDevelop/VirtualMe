from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from anthropic import AsyncAnthropic

from virtualme.interview.guardrail import Guardrail
from virtualme.interview.json_utils import extract_json_payload
from virtualme.interview.models import MODEL_FAST, create_message
from virtualme.interview.turn_state import TurnState
from virtualme.storage.db import Layer

# ruff: noqa: RUF001


class BoundaryStatus(StrEnum):
    NONE = "none"
    EXPLICIT_REFUSAL = "explicit_refusal"
    STRONG_RELUCTANCE = "strong_reluctance"


class EngagementState(StrEnum):
    ENGAGED = "engaged"
    FATIGUED = "fatigued"
    DRIFTING = "drifting"
    GUARDED = "guarded"
    DISTRUSTFUL = "distrustful"


class NextMove(StrEnum):
    ADVANCE = "advance"
    PROBE = "probe"
    HONOR_SKIP = "honor_skip"
    ADDRESS_META = "address_meta"
    SOFTEN = "soften"


@dataclass
class TurnReasonerOutput:
    read: str
    boundary_status: BoundaryStatus
    engagement_state: EngagementState
    next_move: NextMove
    next_question_id: str | None
    should_echo: bool
    echo_content: str | None
    reflection_note: str | None
    reply: str


# Public baseline prompt. Production deployments may provide a private prompt file
# via Settings.reasoner_prompt_file / REASONER_PROMPT_FILE. Keep detailed
# calibration examples and dogfood-derived strategy outside the public repo.
BASELINE_SYSTEM_PROMPT = """You are a careful interview assistant for building a persona profile.

Priorities:
- Respect explicit refusals and reluctance.
- Avoid over-interpreting short-term states as durable traits.
- Use the provided coverage snapshot and candidate questions to choose useful next steps.
- Prefer descriptive observations over psychological labels.
- Output only valid JSON with the requested schema.

Return fields:
read, boundary_status, engagement_state, next_move, next_question_id,
should_echo, echo_content, reflection_note, reply.

Allowed enum values:
- boundary_status: none, explicit_refusal, strong_reluctance
- engagement_state: engaged, fatigued, drifting, guarded, distrustful
- next_move: advance, probe, honor_skip, address_meta, soften
"""

SYSTEM_PROMPT = BASELINE_SYSTEM_PROMPT


def load_system_prompt(path: str | None = None) -> str:
    if not path:
        return BASELINE_SYSTEM_PROMPT
    prompt_path = Path(path).expanduser()
    return prompt_path.read_text(encoding="utf-8").strip()


class TurnReasoner:
    def __init__(
        self,
        client: AsyncAnthropic,
        guardrail: Guardrail | None = None,
        model: str = MODEL_FAST,
        system_prompt: str | None = None,
    ):
        self.client = client
        self.guardrail = guardrail or Guardrail()
        self.model = model
        self.system_prompt = system_prompt or BASELINE_SYSTEM_PROMPT

    async def run(self, state: TurnState) -> TurnReasonerOutput:
        raw_output = await self._call_model(state)
        final_output = self.guardrail.apply(
            output=raw_output,
            current_probe_count=state.probe_count,
        )
        return final_output

    async def _call_model(self, state: TurnState) -> TurnReasonerOutput:
        user_prompt = self._build_user_prompt(state)

        response = await create_message(
            self.client,
            model=self.model,
            max_tokens=900,
            temperature=0.2,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text.strip()

        try:
            data = json.loads(extract_json_payload(raw_text))
            return TurnReasonerOutput(**data)
        except Exception:
            return TurnReasonerOutput(
                read="模型輸出解析失敗，採用保守策略。",
                boundary_status="none",
                engagement_state="engaged",
                next_move="advance",
                next_question_id=None,
                should_echo=False,
                echo_content=None,
                reflection_note=None,
                reply="抱歉，我剛剛思考有點問題。我們繼續剛才的話題好嗎？",
            )

    def _build_user_prompt(self, state: TurnState) -> str:
        history_lines = [
            f"{turn.role}: {turn.content}" for turn in state.recent_history[-8:]
        ]
        history_text = "\n".join(history_lines) if history_lines else "（尚無歷史對話）"

        candidate_lines = [
            f"- [{q.id}] {q.dimension.value}｜{q.text}"
            for q in state.candidate_questions
        ]
        candidate_text = "\n".join(candidate_lines) if candidate_lines else "（無候選題）"

        anchor_lines = []
        for dim, anchors in state.anchors_summary.items():
            if anchors:
                contents = [a.content for a in anchors[:3]]
                anchor_lines.append(f"{dim.value}: {'; '.join(contents)}")
        anchor_text = "\n".join(anchor_lines) if anchor_lines else "（目前尚無 anchors）"

        gap_lines = [
            f"{dim.value}: {gap:.2f}"
            for dim, gap in state.coverage_gaps.items()
            if gap > 0.3
        ]
        gap_text = "\n".join(gap_lines) if gap_lines else "（目前各維度覆蓋尚可）"

        # Build human-readable coverage summary — emphasize what still needs to be collected
        LAYER_LABEL = {
            Layer.FACT: "淺層",
            Layer.PATTERN: "中層",
            Layer.PRINCIPLE: "深層",
        }
        coverage_lines = []
        weak_shallow = []
        for dim, dprog in state.coverage_snapshot.per_dimension.items():
            shallow = dprog.layers.get(Layer.FACT)
            shallow_status = f"{shallow.status}({shallow.quality_score:.2f})" if shallow else "none"
            reached_label = LAYER_LABEL.get(dprog.overall_reached, "無") if dprog.overall_reached else "無"
            coverage_lines.append(f"- {dim.value}: 淺層 {shallow_status} | 已跨 {reached_label}")
            if shallow and shallow.quality_score < 0.5:
                weak_shallow.append((dim.value, shallow.quality_score))

        weak_shallow.sort(key=lambda x: x[1])
        weak_text = ", ".join([d[0] for d in weak_shallow[:3]]) if weak_shallow else "無"

        coverage_text = "\n".join(coverage_lines) + f"\n目前淺層最弱的前三個維度：{weak_text}"
        if not coverage_lines:
            coverage_text = "（尚無收集資料）"

        return f"""【訪談目標】
{state.goal}

【當前問題】
ID: {state.current_question.id}
維度: {state.current_question.dimension.value}
問題內容: {state.current_question.text}

【上一次對受訪者說的話】
{state.last_prompt_text or "（無）"}

【最近對話歷史】（由舊到新，最多顯示 8 輪）
{history_text}

【目前已追問次數】
{state.probe_count}

【已累積的 anchors 摘要】
{anchor_text}

【覆蓋缺口較大的維度】
{gap_text}

【各維度真實收集狀態（coverage_snapshot）】
{coverage_text}

【可選擇的候選題】
{candidate_text}

請依照「思考步驟」嚴格判斷後，輸出 JSON。
"""
