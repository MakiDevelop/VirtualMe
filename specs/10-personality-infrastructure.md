# Personality Infrastructure Strategy

> Status: strategic product direction. This document does not change the
> production interview runtime by itself.

## Thesis

VirtualMe should not be positioned as an AI clone, AI companion, or chatbot.
The stronger framing is:

> Portable personality infrastructure for AI agents.

The asset VirtualMe produces is not a prompt. It is a versioned, portable
persona archive that captures how a person decides, speaks, sets boundaries,
handles tradeoffs, and stays recognizably themselves across model runtimes.

The hard problem is not "can an AI sound like me?" It is:

> Can an AI make choices in a way that preserves my decision style?

## Product Positioning

VirtualMe is a structured personality extraction pipeline:

1. Deep interview collection.
2. Evidence-backed persona anchors.
3. Triangulation across different questions and contexts.
4. Versioned markdown archives owned by the user.
5. Adapters that render the same persona core into different model runtimes.
6. Fidelity tests that detect when a model drifts into its own default persona.

The long-term category is closer to "identity infrastructure for agents" than
to "chat with your AI twin."

## What Counts As Personality

A useful VirtualMe persona should include:

- decision style
- tradeoff hierarchy
- boundary conditions
- contradictions that remain stable over time
- emotional cadence
- cognitive bias and blind spots
- voice and register samples
- domain-specific working habits

Surface-level self-description is insufficient. A user saying "I am principled"
is much less valuable than an observed pattern of what they sacrifice under
pressure.

## Current Strengths

VirtualMe is already pointed in the right direction because it avoids three
common traps:

- It does not rely on form-based profile input, which tends to collect a
  polished self-image.
- It stores evidence as anchors and supports triangulation, so repeated
  patterns can become stronger than isolated statements.
- It treats the persona archive as local, portable, and versionable instead of
  as hidden platform memory.

Recent dogfood also shows the interview can surface useful raw material:

- professional dignity sensitivity
- exhaustion from unreasonable projects
- fatalistic or fate-oriented framing
- emotional restraint under conflict
- trust in explicit ownership and follow-through

These are not finished persona rules yet, but they are meaningful candidate
signals.

## Main Product Risks

### 1. The Full Process Is Heavy

An 8-week pipeline is a differentiator, but it is also a retention risk. Users
need useful artifacts before the final archive.

Suggested milestones:

| Stage | Time | Output |
|---|---:|---|
| Snapshot | 30 minutes | SOUL-lite / first persona sketch |
| v0.1 | 1 week | initial persona archive |
| v0.3 | 3 weeks | contradictions and pressure cases |
| v0.5 | 5 weeks | first blind test |
| v1.0 | 8 weeks | complete persona archive |

### 2. The Interview Can Over-Collect Stories

Stories are necessary, but the most valuable signal is often hidden in a
choice. Engine v2 should move from semantic mining toward decision extraction:

- What did the user choose?
- What did they give up?
- What constraint mattered most?
- What would make them refuse?
- What changes under pressure?

### 3. Cross-Model Fidelity Is A Core Challenge

The same persona archive will behave differently across models:

- Claude may become too consultant-like.
- GPT may become too service-oriented.
- Gemini may over-analyze.
- Grok may over-index on provocation.

VirtualMe therefore needs a model adapter layer and fidelity benchmarks. The
persona core should not be treated as a raw prompt pasted into every model.

## Future Modules

### Decision Style Engine

Extract how a person makes choices under constraint.

Target outputs:

- pressure response
- conflict handling
- tradeoff pattern
- refusal conditions
- escalation threshold
- delegation and ownership style

Interview patterns:

- "What did you choose, and what did you knowingly sacrifice?"
- "What would have made you choose the opposite?"
- "Who did you disappoint, and why was that acceptable?"
- "What constraint was non-negotiable?"

### Contradiction Engine

Personality is not perfect consistency. It is often stable contradiction.

The system should track:

- stated principle vs observed behavior
- desired self-image vs repeated choices
- calm language vs strong emotional trigger
- declared boundary vs tolerated exception

Contradictions should not be treated as errors by default. They should become
explicit persona material when they repeat.

### Timeline Identity

Personality evolves. The archive should know when an anchor belongs to:

- old self
- current self
- aspirational self
- temporary state
- stable trait

This matters because an agent should not over-apply an old pattern after the
user has changed.

### Model Adapter Layer

Architecture direction:

```text
VirtualMe Persona Core
  -> Model Adapter Layer
  -> Claude / GPT / Gemini / Grok / local models
  -> Fidelity Test
```

The adapter layer should translate the same core anchors into model-specific
instructions that counteract each model's default behavior.

### Fidelity Benchmark System

VirtualMe needs tests for whether a runtime still feels like the person.

Possible benchmark tasks:

- blind response selection
- conflict reply roleplay
- tradeoff decision simulation
- boundary refusal test
- voice register matching
- contradiction handling

The benchmark should test choices, not only wording.

## Implications For Interview Engine v2

Engine v2 should add explicit support for:

- decision probes
- tradeoff extraction
- pressure simulation
- controlled friction
- contradiction hunting
- correction passes when the user says "this is not me"

The bot should still protect the user experience:

- one question at a time
- clear purpose when asked
- no endless probing
- pause when the user becomes defensive
- user-controlled skip, pause, and correction commands

## Implementation Priorities

Near term:

1. Keep v1 as production until v2 is feature-flagged and dogfooded.
2. Add v2 adapter and selector behind `VIRTUALME_INTERVIEW_ENGINE=v2`.
3. Extend v2 question metadata with decision/tradeoff targets.
4. Add coarse milestone output such as 30-minute Snapshot.

Mid term:

1. Add decision-style scoring to completeness.
2. Add contradiction candidate storage.
3. Add "unlike me" correction routing to dimensions and anchor types.
4. Add first fidelity benchmark for blind response selection.

Long term:

1. Build the model adapter layer.
2. Track persona archive versions.
3. Benchmark cross-model fidelity.
4. Support portable persona use across agent runtimes.

## Non-Goals

- Do not turn the product into a generic companion bot.
- Do not optimize only for sounding like the user.
- Do not treat a generated summary as a verified persona.
- Do not switch production to v2 before dogfood proves better extraction.
- Do not make contradictions disappear just to produce a cleaner profile.

