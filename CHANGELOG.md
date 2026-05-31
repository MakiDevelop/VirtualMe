# Changelog

All notable changes to VirtualMe are documented here.

## v1.1.1

M2 runtime enforcement for Constitution v1.1 export/snapshot surfaces.

### Highlights

- Added `snapshot.promotion_gate` runtime classifier with `observed` / `recurring` / `cross_session` / `validated` tiers.
- Markdown export no longer treats legacy `triangulated=True` as a validated Core Truth. Same-session 3-question anchors render under `Recurring but Unvalidated Patterns` with missing `cross_session_evidence`.
- Snapshot synthesis now computes anchor source session counts from source turns and caps same-session recurring evidence below stable/high confidence.
- Wired P5 hedge validation into persona export and snapshot export write paths. Generated unhedged stable assertions such as `You are ...` now fail before files are written, while source blockquotes remain exportable as evidence.
- Updated regression coverage for P1/P4/P5 runtime behavior.

### Compatibility notes

- Dimension markdown headings changed from `## Core Truths` to `## Validated Patterns` plus `## Recurring but Unvalidated Patterns`. Downstream parsers that depended on the old heading should update before consuming v1.1.1 exports.
- `triangulated` remains in the DB as a legacy recurring-evidence signal; it is not a validation certificate.

## v1.1.0

在 baseline interview + coverage tracking + persona markdown export 之上，補上 Constitution v1.1（六條 Stability & Restraint Principles）與對應的 M1 hard gates。

### Highlights

- **[Constitution v1.1](specs/11-constitution.md)** — 七位一體 council 2026-05-20 ratified；把先前散落於 `docs/TRUNK.md` / `specs/05` / milestone 的「謹慎、克制、有敬畏」立場 codify 為六條：P1 State-Trait Separation / P2 Contradiction Preservation / P3 Reflective Restraint / P4 Multi-Session Validation / P5 Self-Correction & Agency / P6 Provenance, Confidence & Temporal Decay
- **訪談 reasoning engine 重構** — L0 transport idempotency fail-closed + L1 TurnState 只讀狀態物件 + L2 `turn_reasoner.decide_and_reply()` + Guardrail + feature flag (`reasoning_turn_enabled`) whitelist rollout
- **使用者自助匯出人格檔 + 下載連結**
- **Production demo map** — [`docs/architecture-demo-flow.md`](docs/architecture-demo-flow.md) documents the deployed LINE Bot / VPS architecture and a short demo script.
- **M1 hard gate detectors（4 條）+ 115 contract tests**：
  - P3 — `SkipStopReason` enum + Guardrail metadata + reflection_note no-leak
  - P5 — `hedge_validator`（8 forbidden patterns / 12 hedge markers）+ unlike_me regression
  - P1 — `stability_gate.is_eligible_for_core_truths()`（STATE 不進 Core Truths）
  - P4 — `multi_session_validator.can_be_validated()`（single-session 不得 validated）

> M2 將把 detector wire 進 build_snapshot_bundle / export pipeline；本版只交付 detector + contract test 鎖住 invariant。詳見 `specs/11-constitution.md` §M2/M3。
