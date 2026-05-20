# VirtualMe Constitution v1.1 — Stability & Restraint Principles

> **Status**: Ratified by Chair (Maki) 2026-05-20
> **Date**: 2026-05-20
> **Supersedes**: 散落於 `docs/TRUNK.md` / `specs/05-boundaries-and-pii.md` / milestone notes 的隱性 stance（無 v1.0 單一文件）
> **Council inputs**: Seven-agent council 2026-05-20（synthesis at `~/Documents/agent-council/virtualme/SYNTHESIS.md`）

---

## 0. Preamble — 為什麼有這份文件

VirtualMe 在 v1.0.0 已具備功能基線：結構化訪談、多層 anchor 萃取、可生成詳細 persona representation。技術能力推進到此，**最大風險已從「不夠深」轉為「過度伸手」**——premature crystallization、identity overreach、erosion of human agency。

具體事故 anchor：**2026-05 pilot 中，訪談 bot 越過受訪者明說的情緒邊界，撬出痛苦的個人揭露**（記錄於 `.claude/agent-notes/milestone.md` #16）。這次事件確認：訪談能力本身不會自動避免傷害，必須有顯式的克制機制。

本文件把先前散落於各 spec 與 milestone 的「謹慎、克制、有敬畏」立場 codify 為**可被工程化執行**的六條原則。每條原則包含：
- **Principle Text**（規範文字）
- **Intent**（為什麼）
- **M1 Hard Gate**（v1.1 real-user deploy 前必過）
- **Iterative Scope**（M2/M3 推進）

本憲法**不取代** `specs/05-boundaries-and-pii.md`（PII / consent / 7 條 informed consent）；兩者互補——specs/05 管「不踩 PII / 不冒充治療」的底線；本文件管「萃取 / 合成 / 對外行動」過程中的人格克制。

---

## 1. The Six Principles

### P1. State-Trait Separation

**Principle**:
系統必須在 schema 與 runtime 層級維持「transient state」與「enduring trait」的嚴格區分。Single-session 或單一情境的觀察**不得**寫入穩定 persona representation 為 `validated trait`；只能標 `state` 或 `tentative hypothesis`，附 provenance 與待補 evidence。

**Intent**:
人格心理學共識是 trait 為 state 的密度分佈（Whole Trait Theory），跨情境簽名為其表現（CAPS model）。8 週訪談屬「low session count」情境；自陳 vs 行為觀察 convergent validity 僅 r=0.11–0.31。沒有強約束會把當下情緒寫成「這個人是怎樣」。

**M1 Hard Gate**（real-user prod 前必過）:
- synthesis / export 階段，所有 `Dimension.STATE` 來源 anchor 不得 render 為 SOUL/VOICE/SKILL/BOUNDARIES Core Truths
- 任何 single-session 來源 anchor 必須標 `tentative` 或 `hypothesis`，不得標 `validated`
- contract test 覆蓋：給單一「最近很累」turn → 不得出現於 SOUL.md Core Truths

**Iterative (M2+)**:
- 完整 state/trait promotion pipeline（TTL、cross-context score、ESM-style 情境多樣性 prompt）
- 與 SYNTHESIS-2026-05-18 E11 `target_layer + evidence` 整合

---

### P2. Contradiction Preservation

**Principle**:
系統必須**主動保留**未解的 tension、internal contradiction、不一致 self-description；不得過早 reconcile / 合理化 / 平滑化。矛盾本身被視為人格的有意義組成。當使用者**主動要求**整合詮釋時，方可協助 collapse；系統 default 為並列（juxtaposition），而非合理化（rationalization）。

**Intent**:
McAdams narrative identity 框架認可矛盾為 narrative 演化的主動力；naive dialecticism（東亞傳統）視 contradiction tolerance 為自然認知風格。VirtualMe 是 representation tool，不是治療工具——DBT 的辯證 synthesis 是治療目標，與本文件 scope 不同。

**商業上會被質疑**：市場偏好「clarity / consistent personality」。本原則明知商業張力存在仍保留——這是 VirtualMe 的差異化主張之一（對應 `docs/TRUNK.md` §1.2「非黑盒、訪談 > 填表」），並以 P5 化解：使用者要 clarity 時可主動 collapse。

**M1 Hard Gate**:
- extractor / synthesis 發現新 anchor 與既有 anchor 語意對立時，**禁止覆寫、禁止 merge**；兩者皆保持 `active`
- synthesis renderer 若輸出 SOUL-lite，必須有 `## Unresolved Tensions` 區塊，**禁止**只產出單一調和結論
- 「假裝有做」防線：並列兩句不點出 tension 視為違規；renderer 必須顯式 mark `(tension between W2 and W5)`

**Iterative (M2+)**:
- 顯式 `contradictions` table + `conflict_group_id`（對齊 SYNTHESIS-2026-05-18 E14 Contradiction Buffer）
- contradiction lifecycle（unresolved / contextualized / withdrawn）

---

### P3. Reflective Restraint

**Principle**:
系統的 reflective / interpretive output 的**頻率、深度、framing**必須被 govern。
- 預設**禁止 unsolicited reflection**（系統主動丟「我發現你其實……」類詮釋）
- 在 trauma-relevant context（疲憊 / 拒絕 / 高風險 / 哀傷 / 自殘 / 自殺意念）下**禁止自動加深**，即使使用者主動邀請
- 在非 trauma context 且使用者**明確主動邀請**時，系統可提供 reflective output（permission-gated honor），但仍受 reflection budget 約束、必須 hedging、引用 subject 原話、禁止心理學標籤化

**Intent**:
SAMHSA TIP 57 trauma-informed care：unsolicited reflection 屬 contraindicated。Rogers 的 reflection 需 therapist congruence（真實存在），AI 無法複製。2026-05 #16 incident 是此原則的直接事故 anchor。Character.AI 2024-2026 連環訴訟（含未成年自殺案、Google 1 月和解）+ CA SB 243（2026-01 生效）+ APA 找 FTC 是監管動向背景。

**Counter-evidence acknowledged**: Woebot / Wysa 8 週 RCT 顯示 structured CBT chatbot 有效——但那是**結構化 CBT 介入**，非 open-ended persona reflection，不可直接類比。

**M1 Hard Gate**:
- reasoner output schema 增加 restraint assertion：在 `BoundaryStatus=blocked` / `EngagementState=fatigued|refusing` / `risk_level=high` 時，**禁止** interpretive reflection
- `reflection_note` field 預設 internal-only（audit log），不直接外送
- contract test：trauma / fatigue / refusal fixture 下，reply 不得包含診斷、人格判定、成長敘事
- probe cap 到達時必須 stop / advance 並記 reason metadata（對齊 E15）

**Iterative (M2+)**:
- reflection budget per session（quota + 觸發條件量化）
- Interpretive Adjective Density (IAD) 監測指標
- Post-session dashboarding：將「系統觀察」從對話流移至 snapshot review 階段

---

### P4. Multi-Session Pattern Validation

**Principle**:
任何「stable personality pattern / trait」的宣稱，須由**多 session 跨情境**的 recurrence + consistency 驗證。

**M1 minimum (negative constraint)**: Single-session 來源的 anchor **不得**被標為 `validated`；只能存在為 `tentative` / `hypothesis` / `draft` 等顯式 unvalidated 狀態，並附 provenance 與 missing evidence 說明。

**M2 full gate (quorum)**: 完整 promotion threshold 於 M2 訂定（候選方案：≥2 sessions + ≥3 unique question_ids；或 ≥2 sessions + cross-context evidence）。

**Intent**:
NEO-PI-R 6-year retest r=0.63–0.91；longitudinal personality 研究通常 3–7 年觀察。LLM persona multi-session validation 方法論仍在建立中（TwinVoice、BehaviorChain 為早期 benchmark）。P4 屬「設計保守主義 + 超前業界」，這是優點而非弱點。BehaviorChain (ACL 2025) 顯示 LLM 長序列行為 fidelity 隨 session 下降——P4 本身是有效對沖。

**M1 Hard Gate**:
- `save_anchor` / synthesis 階段，single-session 來源 anchor 路徑禁止標 `validated`
- export wording：未達 quorum 的 anchor 必須以「目前觀察到 / tentative / 待驗證」等語氣呈現，禁止用「You are ...」「Your trait is ...」斷言式
- contract test：3 個來自同一 session 的 anchor 即使 question_id 不同，不得進入 `validated`

**Iterative (M2+)**:
- 完整 promotion pipeline（session count / time span / context diversity score）
- 與 P1 整合的 state→trait promotion gate
- 與 E11 `LayerGateResult` 整合

---

### P5. Self-Correction and Agency

**Principle**:
Persona representation 必須**結構性、程序性**對 subject 開放：modification、denial、supplementation、active rebuttal。系統**不得**自我定位為 final / authoritative interpreter。Subject 是其 narrative identity 的**首要作者**。

**Operational requirements**:
- 每條 persona claim 須附 (a) stability tier（state / tentative / recurring / validated）(b) subject-controlled rebuttal slot (c) version history
- 任何 export / snapshot 須包含可操作的 correction affordance（不只是 markdown 留欄位）
- 系統用語 strictly hedge：「目前觀察到」「根據訪談 W2-W5」「待驗證」；禁止「You are」「Your true self is」式斷言

**Intent**:
- GDPR Art 16 (rectification) + Art 17 (erasure) + Art 22 (automated decision-making) 直接適用 derived persona model
- Taiwan PDPA 第 3 條：查閱 / 複製 / 補充 / 更正 / 停止 / 刪除請求權；2026 PDPC 委員會強化執法
- McAdams：narrative identity 是 internalized and evolving；subject 為首要作者
- Psychology Today 2024：「AI identity theft」心理危害
- Frontiers in Psychology 2025：Algorithmic Self 形成 identity feedback loops
- 競品壓力：OpenHuman (Product Hunt #3 2026 Q2) 主打「memory 屬於使用者」——VirtualMe 必須 match or exceed

**M1 Hard Gate**:
- snapshot / export 全程使用 hedge wording（不可出現 unhedged stable trait 斷言）
- `unlike_me` review 必須能 block downstream promotion（即使原本 multi-session validated）
- 至少一個可操作的 rebuttal 入口（CLI command / LINE 指令 / markdown comment 機制）
- 既有 `restart_interview` / `restart_dimension` / snapshot review (`like_me/unlike_me/unsure/missing_context`) 不得退化

**Iterative (M2+)**:
- `persona_corrections` table：targeted anchor-level rebuttal、status lifecycle
- **Versioning > overwrite**：修正留版本歷史（呼應 P2 矛盾保留；防 uninformed self-editing 引新偏誤）
- Export manifest 記錄 correction state

---

### P6. Provenance, Confidence & Temporal Decay

**Principle**:
每條 persona claim 必須攜帶三個 metadata 欄位：

| 欄位 | 內容 | 對應問題 |
|---|---|---|
| **provenance** | source session_id / timestamp / raw quote ref | 這個 claim 從哪來？ |
| **confidence_tier** | `state` / `tentative` / `recurring` / `validated` | 系統對它多有信心？ |
| **observed_at + staleness_window** | 首次觀察時間 + 信心週期 | 它多舊了？是否需 review？ |

無此三欄位的 claim 不得 surface 到 SOUL / VOICE / BOUNDARIES export。Staleness window 超時的 trait **自動降級為「歷史紀錄」**而非「當前特質」，並觸發定期 review 邀請。

**Intent**:
- **Provenance**: P5 (agency) 的前提——使用者要 rebut 必須知道 claim 從哪來
- **Confidence tier**: P1 / P4 的 surface 表現——使用者一眼能看出哪些是穩定的、哪些是 hypothesis
- **Temporal decay**: NEO-PI-R 6 年 retest A=0.63 顯示 trait 仍會漂移；narrative identity 是「evolving」；persona archive 不能當靜態事實

**M1 Hard Gate (deferred)**: P6 預設**屬於 Iterative scope（M2+）**。M1 不必落完整三欄位，但 export wording 已被 P5 hard gate 約束為 hedged，故不會出現未標來源的 unhedged 斷言。

**Iterative (M2+)**:
- schema 加 provenance / confidence_tier / observed_at / staleness_window 欄位
- staleness auto-downgrade（cron 或 lazy check）
- review 邀請流程：staleness 超時 → 提示 subject「2 週前我們聊到 X，這還適用嗎？」

---

## 2. Cross-Cutting Requirements（跨原則）

### 2.1 P5 cuts across all
P1 / P2 / P3 / P4 / P6 的任何 enforcement 必須**保留 subject override 路徑**。P5 是所有 promotion / classification / rendering 決策的最終 veto。

### 2.2 P3 vs P5 衝突解（permission-gated honor）
使用者明確主動要求 deep reflection 時：
1. 若處於 trauma-relevant context（疲憊 / 拒絕 / 高風險 / 哀傷 / 自殘 / 自殺意念）→ **不 honor**，系統回應「我們暫停一下」並依 `specs/05` §5 處理
2. 若非 trauma context → **permission-gated honor**：可提供 reflective output，但 (a) hedging 語氣 (b) 引用 subject 原話 (c) 禁止心理學標籤化 (d) 仍受 reflection budget 約束

### 2.3 P4 vs P5 衝突解
若系統 validation 過、使用者否認 → **P5 勝**。Validation 是預設、否認是 override。系統不得「辯護」、不得「但根據過去 8 週模式」式回應；應 honor 修正並可詢問「我想理解你說的 X 是指什麼？」（探索而非辯論）。

### 2.4 P2 vs P3 衝突解
P3 restraint 不得讓 P2 contradiction 變隱形。Renderer 必須**顯式 mark tension**（如 `## Unresolved Tensions` 區塊），這不算違反 P3——標註存在性 ≠ 詮釋意義。

### 2.5 與 specs/05 的邊界
- specs/05 管 PII / informed consent / 7 條 / crisis exit / tag-based filtering
- 本文件管 extraction / synthesis / export 中的人格克制
- 衝突時：specs/05 的 crisis exit / informed consent 優先（最高底線）

---

## 3. 治理（Governance）

### 3.1 修訂程序
本文件屬 Layer 5 治理層（對應 `~/.claude/CLAUDE.md` §3 civilization-stack）。任何修訂須走 Council Protocol：
- risk_level >= high → Council deliberation required
- Default Dissenter: Codex
- Chair: Maki
- Output: 帶 evidence ID 的 synthesis + ratify record

### 3.2 與其他文件的關係
- **`docs/TRUNK.md`** 是主幹與路線圖；本文件提供主幹之上的人格克制憲法
- **`specs/05-boundaries-and-pii.md`** 是 PII / informed consent 底線；本文件補上「同意之後」的克制機制
- **`.claude/agent-notes/milestone.md`** 記錄事故 anchor（如 #16）；本文件回應這些 anchor

### 3.3 Open Questions（v1.1 未決，留待後續 council）
1. P4 完整 quorum threshold 的數字（≥2 sessions + ≥3 question_ids 是初步候選，需 M1 dogfood 後再 ratify）
2. P2 commercial narrative：是否要在 README / 對外材料明說「我們刻意不做 clarity 收斂」作為差異化主張
3. specs/05 vs BYOK CONSENT_REPLY 文案落差：v1.1 是否要硬定 specs/05 的 7 條為 single source of truth
4. P6 自動 staleness window：天數 / session 數 / 使用者主動觸發三者的優先序

---

## 4. Ratify Record

| 角色 | Agent | 狀態 | 簽署日期 |
|---|---|---|---|
| Chair | Maki | ✅ Ratified | 2026-05-20 |
| Architect | Claude | ✅ 草案完成 | 2026-05-20 |
| Engineer / Default Dissenter | Codex | ✅ 工程審查 + 2 條 dissent 已納入 | 2026-05-20 |
| Analyst | Gemini | ✅ 設計空間分析 + P6 提案 | 2026-05-20 |
| Local Brain | gemma4 | ✅ 邊界 case 模擬 10 場 | 2026-05-20 |
| Scout-1 (Literature) | Perplexity Max | ✅ 67 學術引用 + P6 提案 | 2026-05-20 |
| Scout-2 (Real-time) | SuperGrok | ✅ 2026 監管 + 競品情報 | 2026-05-20 |

Council 完整證據鏈：`~/Documents/agent-council/virtualme/SYNTHESIS.md`

---

## 5. Version History

- **v1.1** (2026-05-20): 首次 codify。Council ratified（7-agent）。將先前散落於 TRUNK / specs/05 / milestone 的人格克制立場明文化為六條 + 跨原則衝突解。
- **v1.0** (前): 隱性 stance，散落於各 spec 與 milestone，無單一憲法文件。

---

End of constitution v1.1 DRAFT.
