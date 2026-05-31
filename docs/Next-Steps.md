# VirtualMe Next Steps

Updated: 2026-05-31

This note tracks the next pragmatic slices after Constitution v1.1 M1 and M2 runtime enforcement. Keep each item small, testable, and demo-safe.

## Current State

VirtualMe now has:

- Local-first interview storage and question progress tracking.
- Persona markdown export with PII re-scrubbing.
- Snapshot / construct-card review draft generation.
- Blind-test preparation artifacts.
- Constitution v1.1 M1 contract tests.
- M2 runtime promotion gate for export/snapshot surfaces.

Validation baseline:

- `uv run pytest -q` -> 333 passed
- `uv run ruff check src tests` -> passed

## Recently Completed

### M2a. Runtime promotion gate

Implemented:

- `src/virtualme/snapshot/promotion_gate.py`
- Runtime tiers: `observed`, `recurring`, `cross_session`, `validated`
- DB helper to compute anchor source session counts from `source_turn_ids`
- Markdown export sections:
  - `Validated Patterns`
  - `Recurring but Unvalidated Patterns`
  - `Emerging Patterns`
- Snapshot confidence cap for same-session recurring anchors

Important semantic decision:

- `triangulated=True` remains a legacy recurring-evidence signal.
- `triangulated=True` does not mean validated.
- Same-session 3-question anchors must show missing `cross_session_evidence`.

### M2b. Hedge output gate

Implemented:

- Persona export write path calls `assert_no_unhedged_assertions()`.
- Snapshot export write path calls `assert_no_unhedged_assertions()`.
- Generated unhedged stable-trait assertions such as `You are ...` fail before file write.
- Markdown blockquotes are ignored by the gate so raw source evidence can still be exported with provenance.

## Next: M3 Validation Lifecycle

Do not start with a broad migration until Maki confirms policy wording and compatibility needs.

Suggested M3 slices:

1. Add explicit persisted validation fields:
   - `promotion_tier`
   - `validated_at`
   - `validated_by`
   - `validation_source`
2. Add human review promotion policy:
   - cross-session evidence + review can become `validated`
   - `unlike_me` remains a hard veto
3. Add manifest maturity metadata:
   - per dimension tier counts
   - export-level maturity summary
4. Decide compatibility policy:
   - whether to keep an alias for old `## Core Truths`
   - whether downstream consumers must migrate to `## Validated Patterns`
5. Consider P6 temporal decay:
   - stale state downgrade
   - review prompts for old claims

## Open Risks

- `uv.lock` is currently untracked in the working tree and was not adopted by M2 changes.
- The current hedge validator is intentionally conservative and pattern-based. It blocks clear generated assertions but is not a full semantic classifier.

## Defer

- Full scenario generation.
- Agent response generation.
- Shuffle orchestration.
- Gate 2 multi-evaluator workflow.
- Web UI.
- Configurable verdict thresholds.
