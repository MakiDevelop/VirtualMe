# Personality Infrastructure Strategy

> Status: long-range category vision. This is NOT a build spec. It does not
> change the production interview runtime, and nothing in it authorizes work on
> its own.
>
> Near-term priority and "what is on the trunk right now" are governed by
> `docs/TRUNK.md`. Any "Future Module" below stays unbuilt until it passes the
> Trunk Check in `docs/TRUNK.md` §5. On conflict, TRUNK.md wins.

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

Recent dogfood produced some candidate raw material:

- professional dignity sensitivity
- exhaustion from unreasonable projects
- fatalistic or fate-oriented framing
- emotional restraint under conflict
- trust in explicit ownership and follow-through

Caveat: these are unverified candidates, not evidence the engine is working
well. In the dogfood transcript several of them — especially the fatalistic
framing — appeared *because the bot accepted a worldview platitude and stopped
probing*, i.e. they sit at aphorism altitude, not incident altitude (see
`09-interview-engine-v2.md` > Stop Condition: Altitude Criterion). Whether
fatalism is a genuine trait of this interviewee or just a deflection cannot be
decided from the current transcript. Each candidate must be re-drilled per
STG-036 before it becomes persona material.

[未定論] The general question — how to tell "deflection into philosophy" from
"philosophy that is genuinely the person's trait" — is routed to Scout
investigation; see `docs/TRUNK.md` §6.

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

### 3. Cross-Model Fidelity (Real, But A Later Problem)

The same persona archive will behave differently across models:

- Claude may become too consultant-like.
- GPT may become too service-oriented.
- Gemini may over-analyze.
- Grok may over-index on provocation.

This is a real challenge, but it is NOT a near-term risk and NOT in scope for
interview engine v2. It cannot be meaningfully addressed before single-model
fidelity is proven (see Future Modules > Model Adapter Layer, and
`docs/TRUNK.md` §4 trap #8).

[未定論] Whether cross-model portability should be designed in early or retro-
fitted late is a genuine open sequencing question. The judgement that it is "a
later problem" comes from a Claude-authored analysis and therefore carries some
perspective bias. Routed to Scout investigation; see `docs/TRUNK.md` §6.

## Future Modules

> Framing caveat: the items below are written as named "Engines / Layers /
> Systems", but most are *refinements to the single v2 interview + extraction
> pipeline*, not separate subsystems. Decision extraction and contradiction
> tracking should land as pipeline features (tracked under STG-036), not as
> standalone engines.
>
> The Model Adapter Layer and Fidelity Benchmark System are DEFERRED: they must
> not be started until single-model persona fidelity has been demonstrated.
> Starting them earlier is a detour — see `docs/TRUNK.md` §4 trap #8.

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
2. Build the Snapshot thin slice first:
   - SOUL-lite hypothesis synthesis from existing anchors / triples.
   - Mini blind test materials.
   - "This feels unlike me" feedback routing back to dimensions / anchors.
3. Extend v2 question metadata with decision/tradeoff targets and answer
   altitude.
4. Add v2 adapter and selector behind `VIRTUALME_INTERVIEW_ENGINE=v2` only
   after the Snapshot loop can produce a usable feedback signal.

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
