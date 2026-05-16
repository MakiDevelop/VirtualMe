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
- Perplexity Max domain pack: complete 8-field domain supplement archived at
  `docs/research/virtualme-domain-pack-8-fields.md`.
- SuperGrok: product experience flow, progress-aware resume language,
  user-control moments, and repair scripts.
- Strategy reports:
  - `/Users/maki/Documents/VirtualMe_開發建議報告書.md`
  - `/Users/maki/Documents/VirtualMe_深度策略報告書_v2.md`
  - synthesized into [`10-personality-infrastructure.md`](10-personality-infrastructure.md)

Perplexity is used as the question and method backbone. SuperGrok is used as
the conversation experience layer.

The strategy reports add one product constraint to v2: the interview must
extract decision style and tradeoff behavior, not only voice or life-story
material.

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

## Stop Condition: Altitude Criterion

> Added per STG-036 (`~/.claude/mem/staging.md`). Dogfood interviews showed the
> engine stops as soon as the interviewee says anything that *sounds* concrete,
> so it collects worldview platitudes ("命運自有安排", "世事無常", "那是人性") as
> if they were anchors.

A `stop_condition` is satisfied only when the answer reaches **incident
altitude**, not **aphorism altitude**:

- **Incident altitude (stop is allowed)**: a specific time, place, person,
  quoted line, or a choice made under a named constraint — a decision or
  tradeoff with edges.
- **Aphorism altitude (do NOT stop)**: a worldview statement, proverb, or
  fate / human-nature generalization. Treat it as a *deflection*, not an answer.

When an answer is at aphorism altitude, the bot must re-narrow toward a concrete
incident instead of advancing (e.g. "不用是大道理——有沒有一件具體的事，當時你
怎麼選的？"). This re-narrow does not count against `follow_up_max`.

> Open design point: the interaction between this re-narrow and the
> disengagement rule ("two short answers in a row → stop probing") is not yet
> resolved. STG-036 implementation must reconcile them.
>
> Open methodology point: distinguishing "deflection into philosophy" from
> "philosophy that is genuinely this person's trait" is unresolved — routed to
> Scout investigation, see `docs/TRUNK.md` §6.

## Selector Rules

- Prefer staying inside the current dimension until it reaches the completion
  threshold.
- Avoid asking two high-risk questions in a row.
- Do not ask more than two probes for the same question.
- If an answer is at aphorism altitude (see "Stop Condition: Altitude
  Criterion"), do not count the question as satisfied; re-narrow toward a
  concrete incident.
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
- `decision_score`: whether the archive includes explicit tradeoff, pressure,
  refusal, and boundary-decision signals.

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

The current draft packs are in `src/virtualme/data/domain-packs-v2.yaml`.
All 8 Perplexity domain packs have been normalized into structured YAML:

- `engineer_ai_builder`
- `sales_bd`
- `pm_tpm`
- `consultant`
- `manager_people_lead`
- `creator_writer`
- `teacher_coach`
- `founder_operator`

Each pack includes domain metadata, 8 SKILL questions, 5 PEOPLE questions,
5 VOICE roleplays, 5 BOUNDARIES questions, 5 bad-question alternatives, and
12 persona anchor examples.

## Next Implementation Plan

This is the proposed next sequence. The intent is to avoid breaking the current
LINE bot while making v2 concrete enough to dogfood.

### Phase 1: Preserve And Normalize Research Data

Status: done for the first structured draft.

Inputs already saved:

- `src/virtualme/data/question-pool-v2.yaml`
- `src/virtualme/data/domain-packs-v2.yaml`
- `docs/research/virtualme-domain-pack-8-fields.md`

Completed work:

1. Converted the complete Perplexity 8-field domain pack into
   `domain-packs-v2.yaml`.
2. Preserved the raw Perplexity source in
   `docs/research/virtualme-domain-pack-8-fields.md`.
3. Added YAML parse tests and content checks:
   - all 8 domain packs exist
   - each has 8 SKILL questions
   - each has 5 PEOPLE questions
   - each has 5 VOICE roleplays
   - each has 5 BOUNDARIES questions
   - each has 5 bad-question alternatives
   - each has at least 10 persona anchor examples
   - no placeholder such as `{decision_partner}` leaks to user-facing text

Acceptance criteria:

- `ruff check src tests` passes.
- tests prove both `question-pool-v2.yaml` and `domain-packs-v2.yaml` parse.
- production selector still uses the old pool unless a feature flag is enabled.

### Phase 2: Add V2 Data Models And Loader

Add typed models for v2 data without changing the runtime interview flow.

Suggested files:

- `src/virtualme/interview/v2_schema.py`
- `src/virtualme/interview/v2_loader.py`
- `tests/unit/test_interview_v2_loader.py`

Models should include:

- `V2Question`
- `V2DimensionConfig`
- `V2QuestionPool`
- `DomainPack`
- `DomainPackQuestion`
- `VoiceRoleplay`
- `BadQuestionAlternative`

Loader responsibilities:

- parse `question-pool-v2.yaml`
- parse `domain-packs-v2.yaml`
- validate required metadata
- merge domain pack overlays into the generic v2 pool for SKILL / PEOPLE /
  VOICE / BOUNDARIES
- keep user-facing text placeholder-free

Acceptance criteria:

- loader can load generic v2 only
- loader can load generic v2 + `engineer_ai_builder`
- loaded questions retain `purpose`, `user_explain`, `expected_anchor`,
  `follow_up_max`, `stop_condition`, and `risk_level`
- no production route imports v2 loader yet

### Phase 3: Intake Calibration

Before v2 persona extraction starts, the bot must collect domain context.

Required captured fields:

- `domain_role`
- `core_task`
- `primary_counterparty`
- `decision_partner`
- `virtualme_use_case`

Storage options:

- short term: add columns or JSON notes to `subjects`
- cleaner long term: new `subject_profile` / `subject_context` table

Decision needed before implementation:

- whether v2 intake is stored as structured columns, JSON, or anchors.

Recommended first implementation:

- store a JSON object in a new table keyed by `interviewee_id`
- do not count intake toward persona completeness
- let the user update it later with a command like `更新我的領域`

Acceptance criteria:

- a fresh v2 run asks intake before STATE
- if intake is already complete, the bot skips intake and starts STATE
- status reply can show the captured domain context

### Phase 3.5: Decision And Tradeoff Extraction Metadata

Before v2 is used in production, generic and domain questions should identify
whether they collect decision-style signal.

Recommended metadata:

```yaml
decision_targets:
  - tradeoff_hierarchy
  - pressure_response
  - refusal_condition
  - escalation_threshold
  - stable_contradiction
```

Initial implementation can keep this metadata optional. The selector should
eventually prefer questions that fill missing decision targets when anchor
coverage is high but decision signal is weak.

Acceptance criteria:

- at least one question per relevant dimension collects a tradeoff or pressure
  signal
- status/completeness can report when decision signal is still weak
- no v2 production switch until decision targets exist in the draft pool

### Phase 4: V2 Selector Behind Feature Flag

Add a feature flag such as:

```env
VIRTUALME_INTERVIEW_ENGINE=v1|v2
```

V2 selector rules:

- stay within a dimension until it reaches its threshold
- avoid repeated purpose or repeated wording
- avoid two high-risk questions in a row
- respect `follow_up_max`
- after 3-4 questions, offer control and progress
- when a dimension completes, give a short recap and transition
- if the user asks "why", answer with `user_explain`
- if the user says "not me", mark that area for correction instead of arguing

Acceptance criteria:

- v1 remains the default
- v2 can be enabled locally by env var
- no existing v1 tests regress
- v2 has targeted tests for:
  - first question is intake
  - domain context changes SKILL / PEOPLE / VOICE / BOUNDARIES wording
  - high-risk questions are not consecutive
  - repeated questions are avoided
  - decision-target gaps influence selection after basic coverage exists

### Phase 5: Conversation Experience Layer

Implement the parts that reduce boredom and increase ownership.

Required behaviors:

- answer after each user turn with a tiny recap before asking the next question
- explain the purpose when useful, but do not over-explain every turn
- show progress in coarse language
- provide control every 3-4 questions
- ask "does this sound like you?" after dimension recaps
- support correction commands:
  - `這不像我`
  - `你問這幹嘛`
  - `剛剛不是講過了`
  - `跳過`
  - `今天先到這`

Acceptance criteria:

- transcript no longer feels like a questionnaire
- bot can state current dimension, purpose, and approximate progress
- bot stops probing when the user becomes defensive or gives two short answers
- dimension recap produces 2-4 candidate persona anchors, not a long summary

### Phase 6: Dogfood And Switch

Dogfood sequence:

1. Run v2 locally or on a staging flag for one clean interview.
2. Ask status every few turns and verify:
   - current dimension is correct
   - progress is plausible
   - purpose answer is clear
   - no placeholder leaks
3. Export persona anchors and manually inspect:
   - are anchors specific enough?
   - can a responder use them?
   - are there contradictions or generic labels?
4. Only then enable v2 on the VPS bot.

Production switch criteria:

- v2 produces better persona anchors than v1 from the same amount of user effort
- the user can explain why the bot is asking each question
- the user does not feel trapped in endless probing
- the bot can recover from correction without becoming defensive

## Explicit Non-Goals For The Next Pass

- Do not replace production immediately.
- Do not add a web UI.
- Do not implement LINE quick replies before text commands work.
- Do not generate synthetic persona summaries until anchors are good.
- Do not add all possible professions as separate full question pools.
- Do not let domain packs override SOUL / HISTORY / JOURNAL / STATE unless a
  real dogfood transcript proves the generic questions fail.
