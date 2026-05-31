# VirtualMe 工程建議 Review

Date: 2026-05-24
Reviewer: Codex
Scope: repo engineering quality, production dogfood readiness, safety/runtime completeness, deployment and maintenance maturity.

## Executive Summary

VirtualMe 目前不是「批次 prompt 腳本」，而是一個已具備 production dogfood 形態的訪談式人格萃取系統。它已經包含 LINE Bot 入口、FastAPI runtime、SQLite 狀態層、訪談 turn 狀態管理、question selector、follow-up / depth evaluator、PII scrub、anchors、persona export、download token、snapshot / blind-test artifact、BYOK / consent gate，以及一組可觀的 contract tests。

工程成熟度我會評為：

> L2.5 / L5: 可 production dogfood，有真實部署與測試，但還不是成熟產品級開源專案。

最主要的缺口不是「能不能跑」，而是：

1. safety / governance rules 還有一部分停在 detector + contract test，尚未全部 wire 到 runtime export / promotion path；
2. deployment 與 rollback 還偏手動；
3. observability / operator tooling 還薄；
4. mypy strict 設定與實際型別健康不一致；
5. docs 還需要更誠實地標示 Implemented / Dogfood / Roadmap。

如果目標是把 repo 完善成一個站得住的開源專案，下一階段不應該急著加大功能，而應該把 runtime invariants、部署可重複性、資料安全、觀測、dogfood 評估閉環補齊。

## Current State

### 已具備的工程基礎

- Production endpoint: `https://vm.2ch.tw`
- Deployment: VPS `149.28.17.35`, nginx + systemd `virtualme.service` + uvicorn on `127.0.0.1:8000`
- Runtime version: v1.1.0 deployed at commit `e69af45`
- Health endpoint: `/healthz`
- Main transport: LINE webhook `/webhook/line`
- Persistence: SQLite, including sessions, turns, anchors, transport events, persona download tokens/logs
- Test baseline: `pytest` 336 passed at time of review
- Lint baseline: `ruff check .` clean at time of review
- Real dogfood data exists: one production SQLite DB has accumulated turns and anchors

### 已完成的 product / platform pieces

- LINE Bot interview path
- BYOK and consent gate
- Current question tracking
- Follow-up logic and depth evaluator
- Transport idempotency
- PII scrubbing at export boundary
- Persona markdown export
- Tokenized download URL
- Snapshot and behavior profile renderer
- Blind-test preparation path
- Constitution v1.1 detector gates:
  - P1 State-Trait Separation
  - P3 Reflective Restraint
  - P4 Multi-Session Validation
  - P5 Self-Correction & Agency

### 目前最重要的事實

README 已經誠實標示：v1.1.0 的 hard gates 是 detectors + contract tests，M2 才會 wire into `build_snapshot_bundle` / export pipeline。這是好的，但它也代表 production runtime 還不能宣稱完整落實 Constitution。

## Maturity Model

### L1: Prototype

只要能透過 CLI / script 產生初步 persona artifact 即可。

VirtualMe 已超過此階段。

### L2: Functional PoC

具備一條端到端流程：

- 使用者輸入
- LLM 訪談
- 資料儲存
- 初步 persona export
- 基本測試

VirtualMe 已達成。

### L3: Production Dogfood

具備真實部署、真實資料、可重啟服務、基本 health check、基本回歸測試、手動維運流程。

VirtualMe 目前大致在此階段，但 deployment / smoke / rollback 還需要文件化和 script 化。

### L4: Trustworthy Open-Source Project

這是我建議的下一個目標。

需要補齊：

- docs 誠實呈現成熟度與限制
- runtime safety gates 真正接入核心流程
- CI gate 穩定
- deployment 可重複
- migration / backup / rollback 有流程
- production observability 可用
- dogfood review 有閉環

### L5: Small-Scale Product

可以讓非熟人使用，並承擔基本資料安全、錯誤恢復、多使用者邊界、支援與升級責任。

VirtualMe 還沒到這裡，也不需要短期追這個目標。

## Engineering Strengths

### 1. 不是一次性 prompt wrapper

系統已經有以下長期狀態：

- sessions
- turns
- anchors
- question state
- transport events
- export tokens

這代表它不是把一段 prompt 丟給 LLM 的批次工具，而是有訪談流程、狀態機、資料層與 export boundary 的 pipeline。

### 2. 測試密度相對 PoC 來說很好

336 個 pytest 通過，覆蓋範圍包含：

- LINE transport
- BYOK
- commands
- session lifecycle
- question selector
- PII scrub
- export
- download tokens
- schema migrations
- Constitution M1 detector tests

這對個人開源 PoC 來說已經相當扎實。

### 3. 有 production dogfood

系統已部署在 VPS，且有真實 turns / anchors。這點非常重要，因為很多 AI agent repo 停在 notebook / demo script；VirtualMe 已經跨過「只在本機跑」的門檻。

### 4. 治理問題被正面處理

Constitution v1.1 把 personality extraction 的核心風險寫進規格：

- transient state 不可當 stable trait
- single-session 不可 validated
- fatigue / refusal / trauma context 需要 restraint
- unlike_me feedback 需要阻止 promotion
- export wording 需要 hedge

方向是對的。下一步是 runtime enforcement。

## Engineering Weaknesses

### 1. Runtime safety 尚未完整落地

目前 P1/P3/P4/P5 的一部分仍是 detector helpers 與 contract tests。

最明顯的缺口：

- `export/markdown.py` 的 Core Truths 還主要依賴 `anchor.triangulated`
- `DB.save_anchor` 仍以 unique `question_id >= 3` 標記 triangulated
- P4 multi-session validation helper 尚未完整接入 promotion/export
- hedge validator 尚未作為 export/snapshot blocking gate

這會導致文件層已經要求「single-session 不得 validated」，但 runtime 仍可能把同 session 多題的結果呈現得太穩定。

### 2. `triangulated` 和 `validated` 概念仍混雜

目前系統裡 `triangulated=True` 比較像「跨 question 重複出現」，不是「跨 session 被驗證」。這兩者需要拆開。

建議未來明確建模：

- `observed`: 單一 turn / 單一情境
- `recurring`: 多 question 或多情境重複
- `cross_session`: 跨 session 出現
- `validated`: 達成 validation policy，可進穩定 persona surface

### 3. Deployment 仍偏手動

這次 production upgrade 是手動流程：

- SSH
- copy DB backup
- git fetch/pull
- pip install
- init/migrate DB
- systemctl restart
- curl health check

流程正確，但尚未 script 化。下一次如果由不同 agent 或未來的自己操作，風險仍偏高。

### 4. Observability 不足

目前主要依靠：

- `/healthz`
- `journalctl`
- nginx access log

缺少：

- structured logs
- request correlation id
- LLM latency
- export failure rate
- webhook success/failure counters
- DB locked / migration / token download event visibility

### 5. mypy strict 與實際狀態不一致

`pyproject.toml` 設定 mypy strict，但全 repo 實際存在大量 type errors。這會降低工程訊號可信度。

建議不要假裝全 repo strict。短期應改為 scoped mypy，例如只檢查新模組或核心 modules，再逐步擴張。

### 6. Docs 的成熟度標示還可以更清楚

README 很有敘事力，但對開源 reviewer 來說，還需要更清楚的狀態矩陣：

- 已完成
- production dogfood 中
- detector-only
- roadmap
- known limitations

這不是降低氣勢，而是提高可信度。

## Priority Roadmap

## P0 - Repo Hygiene and Truthfulness

Goal: 讓 repo 狀態與 README / docs / production 一致。

Checklist:

- [ ] 補 `docs/maturity.md`
- [ ] README 加上 `Implemented / Dogfood / Roadmap / Known limitations`
- [ ] `docs/architecture-demo-flow.md` 補 `Current vs Planned`
- [ ] 統一 version source，避免 `pyproject.toml`、`__version__`、`/healthz` 分裂
- [ ] 清理或忽略本機未追蹤 `.tmp-audit-bundle.txt`
- [ ] 確認 diagrams / docs 都可在 GitHub 上正常閱讀

Acceptance criteria:

- 新讀者 5 分鐘內可以知道哪些已經可跑，哪些只是 roadmap。
- `git status` clean，沒有奇怪未追蹤 artifact。
- `/healthz` 顯示 version 與 repo tag / commit 可追溯。

## P1 - Runtime Constitution Gates

Goal: 把 Constitution 從 detector 變成 runtime invariant。

Checklist:

- [ ] Core Truths export 不再只看 `triangulated=True`
- [ ] `single-session` evidence 不得進 validated / stable trait surface
- [ ] `Dimension.STATE` 不得 render 到 SOUL/VOICE/SKILL/BOUNDARIES Core Truths
- [ ] export / snapshot 產物跑 hedge validator
- [ ] hedge violation 可 fail export，或至少降級 confidence 並標示 warning
- [ ] `unlike_me` review 寫回 correction / block promotion path
- [ ] 每個 claim 附 provenance + confidence tier
- [ ] 新增 regression fixture:
  - 最近很累
  - 同 session 三題重複
  - explicit refusal
  - fatigue
  - unlike_me
  - high-risk / trauma context

Acceptance criteria:

- 單一 session 即使有三個 question ids，也不會被 render 為 validated Core Truth。
- export 裡不會出現 unhedged stable-trait assertion。
- unlike_me 後同一 claim 不會再次被 promotion。

## P2 - Deployment and Rollback

Goal: production upgrade 可重複、可回滾、可交接。

Checklist:

- [ ] 新增 `scripts/deploy_vps.sh` 或 `docs/deploy-vps.md`
- [ ] deploy flow 固化：
  - preflight git status
  - DB backup
  - fetch / fast-forward only
  - pip install
  - migration
  - restart
  - smoke test
  - log tail
- [ ] 新增 rollback runbook
- [ ] DB backup 命名含 commit + timestamp
- [ ] restore drill 至少跑一次
- [ ] deploy 後自動確認 `/healthz` version / commit

Acceptance criteria:

- 任何 agent 按文件可以在 10 分鐘內安全部署。
- 部署失敗時知道如何回到上一版 code + DB backup。

## P3 - CI and Quality Gates

Goal: GitHub 上的品質訊號可靠。

Checklist:

- [ ] GitHub Actions 跑 `ruff check .`
- [ ] GitHub Actions 跑 `pytest`
- [ ] migration tests 納入 CI
- [ ] mypy 改為 scoped gate，不再宣稱全 repo strict
- [ ] 加 production smoke test script，但不在 public CI 打 real production
- [ ] 加最小 e2e fixture：
  - create DB
  - simulate 3-5 turns
  - generate anchors
  - export persona archive
  - create download token
  - resolve token

Acceptance criteria:

- PR 上能看到 lint/test/migration 狀態。
- main branch 不會在 ruff 或 pytest 紅的情況下繼續發展。

## P4 - Observability and Operator Tooling

Goal: 問題發生時能快速知道是 LINE、LLM、DB、export、download token 還是 user state。

Checklist:

- [ ] structured log schema
- [ ] 不記 raw API key / secrets / PII
- [ ] event types:
  - webhook_received
  - signature_invalid
  - turn_started
  - turn_completed
  - llm_failed
  - anchor_saved
  - export_requested
  - export_denied
  - export_completed
  - token_created
  - token_downloaded
- [ ] operator CLI:
  - `virtualme status <interviewee_id>`
  - `virtualme latest-errors`
  - `virtualme export <interviewee_id>`
  - `virtualme tokens <interviewee_id>`
- [ ] `/healthz` 增強：
  - version
  - commit
  - db reachable
  - schema tables present
  - uptime or started_at

Acceptance criteria:

- 看到一次使用者說「bot 沒回」，可以在 5 分鐘內定位在哪個 layer。

## P5 - Dogfood Evaluation Loop

Goal: repo 的核心問題不是「能不能產生文字」，而是「像不像本人，且能不能被修正」。

Checklist:

- [ ] 設計 5 人 dogfood review template
- [ ] 每人至少一次 export + review
- [ ] 收集：
  - like_me claims
  - unlike_me claims
  - missing context
  - too strong wording
  - privacy discomfort
  - useful surprise
- [ ] unlike_me / missing_context 能回寫 correction layer
- [ ] Week 5 / Week 8 blind test protocol 至少各跑一次
- [ ] 形成 `docs/dogfood-results-template.md`

Acceptance criteria:

- 至少 5 個 dogfood case 能產生具體修正，而不是只收「好像不錯」。
- 可以描述 VirtualMe 最常錯在哪裡。

## P6 - Data Safety and Threat Model

Goal: 因為 VirtualMe 處理的是個人訪談、人格檔、BYOK，資料安全要比一般 demo 更嚴格。

Checklist:

- [ ] threat model
- [ ] BYOK key storage audit
- [ ] download token security review
- [ ] hard delete runbook
- [ ] export archive PII review
- [ ] logs secret/PII scan
- [ ] LINE user id boundary review
- [ ] rate limit / abuse handling
- [ ] backup encryption policy

Acceptance criteria:

- 可以清楚回答：
  - 使用者資料在哪裡？
  - 如何刪除？
  - key 如何撤銷？
  - download URL 洩漏時風險多大？
  - logs 會不會含敏感內容？

## Suggested Next 10 Tasks

1. Create `docs/maturity.md`.
2. Add commit SHA and DB schema status to `/healthz`.
3. Write `docs/deploy-vps.md` from the deployment performed on 2026-05-24.
4. Add production smoke script: healthz, invalid LINE signature, DB table presence.
5. Implement M2 runtime gate for Core Truths export.
6. Add hedge validator to export/snapshot output checks.
7. Split `triangulated` vs `validated` semantics.
8. Add scoped GitHub Actions: ruff + pytest.
9. Add dogfood review template.
10. Decide whether `.tmp-audit-bundle.txt` should be removed, ignored, or moved outside repo.

## Technical Completeness Scorecard

| Area | Score | Notes |
|---|---:|---|
| Core interview flow | 7/10 | Real LINE dogfood exists; flow has state and extraction. |
| Persistence model | 7/10 | SQLite is appropriate for dogfood; schema migrations exist. |
| Persona export | 7/10 | Useful archive + download token exists; runtime safety gate needs M2. |
| Safety/governance | 6/10 | Strong specs and detector tests; runtime enforcement incomplete. |
| Test coverage | 8/10 | 336 tests is strong for this phase. |
| Type health | 3/10 | mypy strict config does not match actual state. |
| Deployment | 5/10 | Production exists; deploy is still manual. |
| Observability | 4/10 | healthz + journalctl only; structured app telemetry missing. |
| Documentation | 6/10 | Strong narrative and specs; needs maturity/status matrix. |
| Open-source readiness | 6/10 | Usable and interesting; needs CI, runbooks, clearer limitations. |

Overall: 6.2/10 for an open-source production dogfood project. The project is well past a toy demo, but the next work should be mostly engineering hardening rather than feature expansion.

## Recommended Positioning

The most accurate technical positioning is:

> VirtualMe is a local-first, interview-driven persona extraction pipeline with a production dogfood LINE Bot. It is designed to generate user-owned persona artifacts from multi-session interviews, with privacy, provenance, correction, and validation as first-class engineering concerns.

Avoid claiming:

- mature SaaS
- fully validated AI twin
- complete runtime safety enforcement
- production-grade multi-user platform

Safe claims:

- production dogfood
- open-source pipeline
- LINE Bot + FastAPI + SQLite
- persona archive export
- safety detector gates
- blind-test oriented workflow
- user-owned markdown artifacts

## Closing Recommendation

Do not rush toward more visible features until the following three are done:

1. Runtime Constitution gates.
2. Deploy / rollback / smoke-test runbook.
3. Maturity docs and CI.

These three will make the repo much harder to dismiss and, more importantly, much easier for future Maki / Claude / Codex / Gemini sessions to improve without accumulating hidden risk.
