# Interview Engine v2 Draft

> Status: draft only. This does not replace the production question pool yet.

## Goal

Interview Engine v2 should produce usable persona anchors, not just long
conversation transcripts. Every question must know:

- which dimension it is collecting
- what persona signal it expects
- when to probe
- when to stop
- how risky or tiring the question is
- how to explain its purpose to the interviewee

The guiding product rule is: if the user asks "why are you asking this?", the
bot must have a short, honest answer.

## Source Inputs

This draft combines two scout outputs:

- Perplexity Max: methodology-first question design, 57 core questions,
  anchor type, stop condition, and risk notes.
- SuperGrok: product experience flow, progress-aware resume language,
  user-control moments, and repair scripts.

Perplexity is used as the question and method backbone. SuperGrok is used as
the conversation experience layer.

## Conversation Flow

Default order:

0. INTAKE: ask the interviewee's domain, role, core tasks, counterparties, and
   expected VirtualMe use cases.
1. STATE: warm start from current reality.
2. HISTORY: build the timeline and turning points.
3. SOUL: infer values from choices, not labels.
4. PEOPLE: trust, collaboration, influence, and relationship boundaries.
5. SKILL: work method, decision process, craft habits.
6. JOURNAL: reflection, self-correction, and meaning-making.
7. BOUNDARIES: refusal, authorization, and hard limits.
8. VOICE: concrete message samples and roleplay for responder fidelity.

This order is intentionally different from the old week-based pool. It starts
safe and concrete, then moves inward, then ends with reusable voice samples.
INTAKE is not counted as persona completion. It calibrates placeholders and
keeps the rest of the interview from sounding generic.

## Intake Calibration

Before asking persona questions, the bot should collect four setup facts:

- `domain_role`: what kind of professional / role the person is.
- `core_task`: the main kind of work or decisions they repeatedly handle.
- `primary_counterparty`: who they most often interact with.
- `decision_partner`: who they negotiate priority, scope, budget, or tradeoffs with.

Example:

```yaml
domain_role: "AI PoC / TPM / software-adjacent operator"
core_task: "researching AI tools, deciding architecture, and driving PoC delivery"
primary_counterparty: "engineers, stakeholders, and agent collaborators"
decision_partner: "technical partners or business owners deciding scope"
```

If the user does not want to define this upfront, the bot should use broad
language and keep asking domain-agnostic questions until enough context is
observed.

## V2 Question Schema

```yaml
- id: state_01
  dimension: STATE
  stage: warmup
  text: "最近這陣子生活過得怎麼樣？有什麼事讓你特別有動力，或是有點壓力？"
  purpose: "捕捉當前情緒、壓力源、能量來源、短期目標。"
  user_explain: "我想先從你現在的狀態開始，這樣 VirtualMe 回覆時比較貼近你目前的感受。"
  expected_anchor: fact
  acceptable_answers:
    - daily_story
    - emotion
    - concrete_example
  follow_ups:
    - "它最近大概佔了你多少心力？"
    - "你通常怎麼處理這種狀態？"
  follow_up_max: 2
  stop_condition: "取得 1-2 個具體事項與感受，或使用者想換話題。"
  risk_level: low
  optional: false
```

## Selector Rules

- Prefer staying inside the current dimension until it reaches the completion
  threshold.
- Avoid asking two high-risk questions in a row.
- Do not ask more than two probes for the same question.
- If the user gives two short or defensive answers in a row, stop probing and
  switch to a safer question.
- If the user asks for progress or purpose, answer that meta question before
  continuing.
- If a dimension has enough fact anchors but weak principle anchors, select a
  principle question in the same dimension.
- If a dimension has enough anchors but low voice fidelity, move to VOICE
  roleplay.

## Progress Model

Engine v2 should not rely on anchor count alone. Use three scores:

- `coverage_score`: active anchors per dimension.
- `scope_score`: how many dimensions have at least one usable anchor.
- `yield_score`: whether anchors include fact, pattern, and principle layers.

Initial implementation can keep the existing weighted completeness score, but
the UI copy should expose only coarse ranges.

Suggested ranges:

- 0-20%: warm start, low pressure.
- 20-50%: enough context for early patterns.
- 50-80%: deeper values and boundaries.
- 80-95%: voice samples and final gaps.
- 95%+: recap, correction, and "what feels unlike you?" pass.

## User Control

Every 3-4 questions, the bot should offer control:

- continue
- switch topic
- pause
- ask progress
- correct what feels wrong

LINE quick replies can implement this later. For now, plain text commands are
enough.

## Repair Scripts

When the user says "這不像我":

> 抱歉，是我理解錯了。你可以直接改我：哪一段不像你？我會把這段標成需要重訪談，不會拿它當定論。

When the user says "你問這幹嘛":

> 這題是想補【{dimension}】裡的 {purpose_short}。如果你覺得不重要，我們可以跳過，完全沒問題。

When the user says "剛剛不是講過了":

> 對，你前面有提到 {recap}。我原本是想從另一個角度確認；如果已經夠清楚，我們直接換下一題。

When the user shows fatigue:

> 我們先停在這裡。你前面說的已經足夠保存，之後可以從這題接，不需要重來。

## Migration Plan

1. Add `question-pool-v2.yaml` as draft data only.
2. Add intake command/state for domain calibration.
3. Add `domain-packs-v2.yaml` as optional domain-specific overlays.
4. Add a loader that accepts v2 metadata while keeping old `Question` usable.
5. Add tests for placeholder-free text, risk metadata, and anchor target fields.
6. Add selector v2 behind a feature flag.
7. Dogfood v2 with one interviewee before replacing production default.

## Domain Packs

Domain packs should not replace the eight-dimension persona backbone. They only
specialize the dimensions where professional context matters most:

- SKILL
- PEOPLE
- VOICE
- BOUNDARIES

The first draft pack is `engineer_ai_builder` in
`src/virtualme/data/domain-packs-v2.yaml`. Remaining packs should be added only
when Scout output includes complete questions, roleplay scenarios, bad-question
alternatives, and persona anchor examples.
