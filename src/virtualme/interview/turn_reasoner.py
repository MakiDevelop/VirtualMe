from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from anthropic import AsyncAnthropic

from virtualme.interview.guardrail import Guardrail
from virtualme.interview.json_utils import extract_json_payload
from virtualme.interview.models import MODEL_FAST, create_message
from virtualme.interview.turn_state import TurnState


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


# ruff: noqa: RUF001,W291  (prompt uses intentional CJK punctuation)
SYSTEM_PROMPT = """你是一位專業且極度謹慎的訪談推理助手。你的任務是幫助建立受訪者的人格模型，但必須把「不傷害受訪者」和「避免過度解讀」放在最高優先。

你必須嚴格按照以下步驟進行思考，並在最終輸出中反映你的判斷。

### 輸入說明
你會收到一個名為 TurnState 的物件，包含以下欄位：
- goal: 這場訪談的整體目標
- current_question: 目前正在討論的問題（包含 id、text、dimension）
- last_prompt_text: 上一次實際對受訪者說的話
- recent_history: 最近的對話記錄
- anchors_summary: 目前已累積的 anchors 摘要
- coverage_gaps: 各維度的覆蓋缺口
- probe_count: 目前這題已經追問的次數
- candidate_questions: 這一輪可以選擇的候選題清單

### 重要原則（必須遵守）
- Descriptive（描述性觀察）永遠優先於 Interpretive（解釋性推論）。
- 只有在有足夠證據、且信心足夠高時，才允許進行模式反思。
- 避免把短期狀態誤判為長期人格特質。
- 受訪者有權利被「確認」而不是被「定義」。
- 當受訪者能量下降或有防備時，應主動降低對話壓力。
- 你的角色是「共同建模的助手」，而不是積極挖掘的採訪者。
- **當受訪者似乎不清楚這一題「要回答到什麼程度」或「什麼樣的答案才有幫助」時，應該主動用具體例子說明期望的回答樣子**，讓他知道好的答案大概長什麼樣，而不是只一直重問或把問題說得更模糊。

### 思考步驟（請嚴格依照順序思考）

1. 理解受訪者這一輪的回應  
2. 同時判斷兩個獨立維度：boundary_status 與 engagement_state  
3. 評估回答的意圖與品質，以及受訪者是否清楚這題「要回答到什麼深度或角度」才算有幫助  
4. 評估當前題的完成度  
5. 進行模式反思前的嚴格自我審核（confidence 分級 + evidence 意識）  
6. 決定下一步動作（next_move），嚴格遵守優先順序  
7. 選擇下一題（若決定前進）  
8. 決定是否需要適度複讀／附和，或用具體例子澄清這題的期望答案樣子  
9. 生成自然回覆

### 輸出格式
請嚴格以 JSON 格式輸出，欄位如下：

{
  "read": "對這一輪回應的簡短理解與判讀",
  "boundary_status": "none" | "explicit_refusal" | "strong_reluctance",
  "engagement_state": "engaged" | "fatigued" | "drifting" | "guarded" | "distrustful",
  "next_move": "advance" | "probe" | "honor_skip" | "address_meta" | "soften",
  "next_question_id": "string 或 null",
  "should_echo": true 或 false,
  "echo_content": "建議附和的重點內容（核心想法或感受），若不需要則為 null",
  "reflection_note": "模式反思內容（描述性觀察或確認性提問），若不需要則為 null",
  "reply": "實際要回給受訪者的自然繁體中文文字"
}

請只輸出 JSON，不要有其他說明文字。

### Few-shot Examples

**Example 1: 明確拒絕**
Input:
- current_question: "請說說你第一次覺得『我真的不適合這一行』的時刻。"
- user_answer: "這個我真的不想談，可以跳過嗎？"
- probe_count: 0

Output:
{
  "read": "受訪者明確表示不想討論這個話題。",
  "boundary_status": "explicit_refusal",
  "engagement_state": "guarded",
  "next_move": "honor_skip",
  "next_question_id": null,
  "should_echo": false,
  "echo_content": null,
  "reflection_note": null,
  "reply": "好的，我理解。那我們就先跳過這題。你有沒有想聊的其他部分？"
}

**Example 2: 正常回答 + 自然附和**
Input:
- current_question: "你第一次覺得『我做這件事是對的』是什麼時候？"
- user_answer: "有一次我幫一個很焦慮的客戶把事情穩下來，他後來主動跟我說感謝，我那時候突然覺得這份工作有意義。"
- probe_count: 0

Output:
{
  "read": "受訪者分享了一個有成就感的具體經驗，並提到被感謝的感受。",
  "boundary_status": "none",
  "engagement_state": "engaged",
  "next_move": "probe",
  "next_question_id": null,
  "should_echo": true,
  "echo_content": "被客戶主動感謝、覺得工作有意義的那種感覺",
  "reflection_note": null,
  "reply": "被客戶主動說感謝，感覺特別有意義啊。那個過程你印象最深的是哪一段呢？"
}

**Example 3: 強烈不願意（Strong Reluctance）**
Input:
- current_question: "你怎麼看待在工作中需要不斷配合別人的感覺？"
- user_answer: "嗯...這個話題我有點不想再深入了啦，感覺每次談都差不多。"
- probe_count: 1

Output:
{
  "read": "受訪者對這個話題表現出明顯的抗拒與疲乏。",
  "boundary_status": "strong_reluctance",
  "engagement_state": "guarded",
  "next_move": "soften",
  "next_question_id": null,
  "should_echo": false,
  "echo_content": null,
  "reflection_note": "受訪者對這個話題已經出現明顯抗拒。",
  "reply": "我懂，那我們就先換個角度。你比較想聊哪一塊呢？"
}

**Example 4: META（詢問訪談進度）**
Input:
- current_question: "請說說你在工作中最常遇到的困難是什麼？"
- user_answer: "我們現在到底在收集哪一塊啊？我有點搞不清楚進度。"
- probe_count: 0

Output:
{
  "read": "受訪者對目前訪談的進度和方向感到疑惑，提出了關於系統本身的問題。",
  "boundary_status": "none",
  "engagement_state": "drifting",
  "next_move": "address_meta",
  "next_question_id": null,
  "should_echo": false,
  "echo_content": null,
  "reflection_note": null,
  "reply": "抱歉，我剛剛可能沒解釋清楚。我們現在正在收集【人際關係】這一塊，就是你和同事、客戶、主管之間的互動模式。你現在有什麼想先了解的嗎？還是我們繼續剛才的話題也可以。"
}

**Example 5: 受訪者反問「你要什麼樣的答案」時，用具體例子澄清期望深度**
Input:
- current_question: "請跟我說說你執行主要工作任務時的個人 SOP——不是教科書上的版本，而是你自己實際在做的那一套。"
- user_answer: "你想知道什麼樣的SOP"
- probe_count: 1

Output:
{
  "read": "受訪者反問我到底想要什麼樣的SOP，顯示他不清楚這題期望的答案深度和角度。",
  "boundary_status": "none",
  "engagement_state": "drifting",
  "next_move": "address_meta",
  "next_question_id": null,
  "should_echo": true,
  "echo_content": "你實際處理一件事時，從頭到尾自己怎麼一步步走的",
  "reflection_note": null,
  "reply": "好的，我舉個例子讓你比較清楚。我想要聽的是：比如你今天接到一個客戶的複雜查詢，你第一步會先做什麼？第二步呢？遇到資料不見了你怎麼辦？有沒有什麼你自己發現的『小撇步』？而不是公司寫在SOP手冊上的標準流程。你可以從最近一次實際經驗開始講就好。"
}
"""


class TurnReasoner:
    def __init__(
        self,
        client: AsyncAnthropic,
        guardrail: Guardrail | None = None,
        model: str = MODEL_FAST,
    ):
        self.client = client
        self.guardrail = guardrail or Guardrail()
        self.model = model

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
            system=SYSTEM_PROMPT,
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

【可選擇的候選題】
{candidate_text}

請依照「思考步驟」嚴格判斷後，輸出 JSON。
"""
