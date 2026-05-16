# VirtualMe — 主幹與路線圖（Trunk & Roadmap）

> 用途：定義 VirtualMe 的**主幹路線**、各階段預期發展、以及一個可定期執行的「有沒有繞路」檢查。
> 建立：2026-05-16 by Claude (Architect)
> 性質：活文件。每次階段轉換或月度 review 後更新 §1.4 與 §3 的「現況」。
> Review 方式：見 §5。
> 與其他文件關係：`specs/*` 是設計細節；本檔是上位的方向約束。衝突時，本檔的「主幹定義」優先於任何單一 spec 的深化。

---

## 0. 接續錨點（Handoff Anchor）— 新 session / 新 agent 從這裡開始

> 這格是 VirtualMe 所有工作的**單一接續點**。任何人或 agent 接手 VirtualMe，
> 先讀這格 → 再跑 §5.1 Trunk Check → 再依 §7 認領自己那一棒。
> **規則**：每個動到 VirtualMe 的 session 結束前，必須更新這格 + 寫 memhall（`namespace: project`，
> 內容指回本檔）。這樣下一棒不論是哪個 agent、哪個 session，都從同一個事實接手。

**最後更新**：2026-05-16（晚間）by Codex (Engineer/Dissenter)

**當前階段**：S4/S5 前置 — ⚠️ 端到端薄切片（onboard→驗證）**尚未打通過一次**（見 §2.1 / §3.0）。
S2 訪談 plumbing 已改善；下一個主幹缺口不是更多題目，而是 Snapshot 的合成與驗證。

**當前焦點**：① 打通 Snapshot 薄切片（訪談資料 → SOUL-lite hypothesis → mini blind test）②
把 STG-036 的 altitude / decision-target 設計排進 v2，但不在 Snapshot 前擴大題庫。

**進行中**：

| 項目 | 負責 | 狀態 | 檔案 |
|---|---|---|---|
| 5 個 plumbing bug 修正 | Codex | ✅ 已修並 commit（`a726cd8` / `fbd7ca6`），訪談 2 驗證生效 | — |
| 重新定位 dissent | Codex | ✅ 已完成：reposition 可作 north star，但近期路標改成 Snapshot / SOUL-lite / mini blind test 優先 | 本檔 §8 |
| STG-036 萃取深度重構 | Claude → Max → Claude | 已 amend（決策 vs 格言判準 + 矛盾狩獵），待 Maki ratify | `~/.claude/mem/staging.md` STG-036 |
| 生命週期 3 批調查 | ChatGPT / Max / SuperGrok | 問題清單已備 | 本檔 §6 |

**下一步（單一最重要）**：先做 Snapshot 薄切片的工程端：SOUL-lite synthesis + mini blind test。
STG-036 進 v2 設計與後續 feature flag，不阻塞 Snapshot 第一版。

**Blockers / 已確認**：S4/S6 不是空白，但都只是骨架：
S4 有 `export/markdown.py` 將 anchors 匯出成 dimension markdown，**沒有**真正的 SOUL-lite / persona synthesis；
S6 有 `responder/core.py` + `responder/persona.py` responder skeleton，但目前偏 HR/HRBP demo，**不是**通用 persona runtime。

---

## 1. 來龍去脈

### 1.1 市場起點

市面上有一批「打造你的 AI 分身」課程，賣 $3,000–5,000 USD。它們其實賣三件事：

1. 教你填 SOUL.md / SKILL.md 之類的人格檔案
2. 教你串 Claude / OpenAI API
3. 同儕網絡 + 督促 + 教練回饋

技術上，第 1、2 件不值 $4,000。第 3 件（人的督促）才是這些課程真正的留存機制。

### 1.2 VirtualMe 的賭注

VirtualMe = 第 1、2 件事的開源版本，並把第 1 件從「自己填表」換成「**被訪談**」——
8 週訪談把一個人萃取成 AI 代理人。

兩個核心差異化：

- **非黑盒**：產出是使用者自己擁有、看得到、改得回的 markdown（SOUL / VOICE / BOUNDARIES），
  不是某天會 silently update 的雲端產品。
- **訪談 > 填表**：人不擅長自我描述。訪談 + 追問能挖出填表挖不到的東西。

⚠️ **賭注的隱藏成本**：VirtualMe 刻意不做課程的第 3 件事（教練/同儕督促）。
那正是課程的留存引擎。VirtualMe 等於拿掉了留存引擎——這是 S0/S1 最大的結構性風險（見 §3）。

### 1.3 已經建好的（2026-05-16）

| 層 | 狀態 |
|---|---|
| 設計 spec | `specs/00`–`10` 齊全：overview / 訪談引擎 / 題庫 / blind-test / tech-stack / PII / 三方案 / related-work / 記憶架構 / 引擎 v2 draft / personality infrastructure strategy |
| 訪談引擎 v1 | production，跑在 VPS LINE bot（`149.28.17.35`）|
| 訪談引擎 v2 | draft：`question-pool-v2.yaml`（5 intake + 64 泛用）、`domain-packs-v2.yaml`（8 領域，Codex 剛完成機械轉換 + 測試）|
| 萃取 | `anchor_extractor.py` / `triples.py` / `depth_evaluator.py` 存在 |
| 驗證 | `blind_test.py` + `specs/03` blind-test protocol |
| 合成 | `export/markdown.py` 只輸出 anchors，不是 synthesis；缺 SOUL-lite 合成 |
| Runtime | `responder/` 有 demo skeleton，但非通用 persona runtime |
| 維護 | 「重頭開始萃取」指令（commit `ce2e857`）、`week_progression.py` |

### 1.4 現在站在哪（每次 review 更新這格）

**2026-05-16**：跑了一場真實訪談（約 40 回合），暴露兩件事：

1. **5 個編排層 plumbing bug** → 已開 Codex briefing 修正（`agent-council/20260516-virtualme-interview-fixes/`）。
2. **一個設計問題**：引擎在收場面話——40 回合只萃到 1 個有辨識度的錨點。
   `stop_condition` 太鬆、追問只有一招 → 已開 **STG-036**。

**判斷**：VirtualMe 目前把力氣集中在 **S2（訪談）的內容深化**（8 領域、64 題、v2 題庫），
但 **S4（合成）→ S5（驗證）的端到端迴路從未被打通驗證過**。這是典型的繞路前兆——
見 §2。

---

## 2. 主幹定義（The Trunk）— 本檔最重要的一節

### 2.1 一句話主幹

> **VirtualMe 的主幹是：一個人走完「onboard → 訪談 → 萃取 → 合成 persona → 自己驗證『像不像我』」
> 的完整迴路，並且他能在最後說出『這像我』。**

不是「題庫多完整」、不是「訪談多順」、不是「8 領域多齊」。
是**那個人最後有沒有認出自己**。

### 2.2 主幹原則：薄切片優先（breadth-first thin slice）

VirtualMe 有 8 個使用者階段（S0–S7，見 §3）。兩種推進方式：

- ❌ **深度優先**：把 S2 訪談做到完美，再做 S3，再做 S4……
  → 風險：在 S4/S5 才發現「萃取出來的東西根本合不成一個人」，前面全部白做。
- ✅ **薄切片優先**：先用**最小可行**的每個階段，打通一條 onboard→驗證的細線，
  讓「像不像我」這個訊號**真的跑出來一次**。然後才回頭加深。

**主幹 = 那條最細的端到端線。** 任何在某個階段「加深」但該階段的薄切片還沒打通的工作，
預設視為繞路，要先停下來問「這有沒有讓端到端迴路更接近跑通」。

### 2.3 什麼算「在主幹上」 / 什麼算「繞路」

| 在主幹上 ✅ | 繞路 ⚠️ |
|---|---|
| 讓「像不像我」訊號第一次端到端跑出來 | 在迴路跑通前，把題庫從 64 題擴到 120 題 |
| 修阻斷迴路的 bug（如模板洩漏） | 修不影響迴路的體驗細節 |
| STG-036：讓萃取真的萃到「人」 | 把 8 領域加到 16 領域 |
| 打通 S4 合成、S5 blind-test | 為還沒驗證的引擎做 dashboard / 多語系 / router |

---

## 3. 各階段：現況 / 預期發展 / 主要風險 / 完成判準

> 「預期發展」是 Claude 的**預測**，不是承諾——用來在 review 時對照「實際是否偏離」。
> 「完成判準」= 該階段薄切片打通的定義（Definition of Done）。

### 3.0 里程碑階梯（薄切片的時間軸具體化）

§2.2 的「薄切片優先」落到時間軸 = 下面這條階梯。每一階是一條**更完整的端到端線**，
不是「把某個階段做深」。借鑑外部策略報告，經主幹原則篩選後採用。

| 里程碑 | 時間 | 產出 | 打通哪些階段 |
|---|---|---|---|
| **Snapshot** | 30 分鐘 | SOUL-lite（極簡人格初稿） | S0→S1→S2(極短)→S3(極簡)→S4(lite) — **第一條端到端細線** |
| v0.1 | 1 週 | 初步人格檔 | 上述各階段加厚一層 |
| v0.3 | 3 週 | 加入反例與衝突情境 | S2 加 decision probe / 矛盾狩獵 |
| v0.5 | 5 週 | **第一次 blind test** | S5 首次端到端跑出「像不像我」訊號 ← 主幹終點首達 |
| v1.0 | 8 週 | 完整 persona archive | 全階段加深 |

**讀法**：Snapshot 就是 §2.1 主幹的最小實現——30 分鐘內讓一個人走完整條線拿到 SOUL-lite。
但 SOUL-lite 是 **hypothesis / draft**，不是「30 分鐘就準確萃取出你」的承諾。第一版成功的判準是：

1. 從現有訪談資料產出一份明確標示信心與 provenance 的 SOUL-lite。
2. 本人能逐條標記「像 / 不像 / 不確定」。
3. 產出一組 mini blind test 材料，讓「像不像我」訊號第一次端到端跑出來。

在 Snapshot 跑通前，任何「加深單一階段」的工作預設是繞路。
S0–S7 的「完成判準」不是一次達成，而是隨階梯每一階逐步加厚。

### S0 — 取得與承諾（Acquisition & Commitment）

- **現況**：開源 repo + README 是入口。使用者自行 clone 自架，或用 Maki 託管的 bot。
- **預期發展**：自架門檻高 → 多數人會用託管 bot → 「非黑盒、資料自己擁有」的賣點在託管模式下被稀釋（資料在 Maki 的 VPS）。需要一套清楚的「自架 vs 託管」信任說明。
- **主要風險**：① 8 週承諾 + 無教練督促（§1.2）→ 完成率可能極低 ② 託管模式稀釋核心賣點。
- **完成判準**：一個新使用者能在 5 分鐘內理解「這要 8 週、產出是什麼、資料在哪」並啟動。

### S1 — Onboarding & Intake

- **現況**：5 題 intake → 選 1 個 domain pack（8 選 1）。
- **預期發展**：單一 domain pack 指派會撞牆——真實的人是混合的（會帶人的工程師、會賣的創辦人）。預期需要演化成「多 pack 加權」或「主+副 pack」。
- **主要風險**：① intake 誤判 → 錯的題組跑滿 8 週 ② 期待落差（以為是聊天機器人，結果是訪談）。
- **完成判準**：intake 後使用者拿到的題組，他自己認同「這些問題問對方向」。

### S2 — 訪談 / Elicitation

- **現況**：v1 production、v2 draft。剛驗證出「收場面話」問題（STG-036）。
- **預期發展**：STG-036 重構後，預期能萃到更具辨識度的回答；但 8 週長訪談的疲勞、心情依賴、自我美化（espoused vs enacted）會是下一層問題。
- **主要風險**：① 收場面話（STG-036 處理中）② 自我report 偏誤——人描述理想自我不是真實行為 ③ 8 週疲勞與 disengagement。
- **完成判準**：一場訪談結束後，逐字稿裡可辨識錨點密度 ≥ 某門檻（非「對話順不順」）。
- **註**：訪談**技術**層面的調查已在 STG-036 的 `max-questions.md`，本檔不重複。

### S3 — 萃取 / Anchoring

- **現況**：`anchor_extractor.py` / `triples.py` / `depth_evaluator.py` 存在。
- **預期發展**：跨週矛盾（第 1 週說 X、第 5 週說 ¬X）會浮現——人本來就不一致，把矛盾壓平等於弄丟這個人。預期需要「保留矛盾」而非「解決矛盾」的設計。
- **主要風險**：① LLM 萃取幻覺/過度推論 ② 矛盾被壓平 ③ 錨點過度擬合單一軼事。
- **完成判準**：萃取出的錨點，使用者能逐條判斷「是/不是我」，且「是」的比例可量。

### S4 — Persona 合成（SOUL / VOICE / BOUNDARIES）

- **現況**：已確認只有 archive export skeleton。`src/virtualme/export/markdown.py` 會把 anchors 依 dimension 輸出成 markdown，但它不是合成模組；缺少「anchors → SOUL-lite / VOICE-lite / BOUNDARIES-lite」的摘要、取捨、信心標記與反饋入口。
- **預期發展**：最大難關。① LLM 拿到 persona prompt 會「回歸通用助理基線」，把獨特性磨平 ② VOICE（怎麼講話）比 SOUL（想什麼）難太多 ③ 一串錨點 ≠ 一個連貫的人。
- **主要風險**：① 回歸通用基線 ② VOICE 無法靠 markdown 重現 ③ 可編輯性悖論——使用者編輯自己的 twin = 虛榮編輯 → twin 偏離真實（透明性賣點同時是準確性風險）。
- **完成判準**：合成出的三個 markdown 餵給 LLM，能跑出一段「使用者認得出是自己」的對話。

### S5 — 驗證 / Blind Test

- **現況**：`specs/03` + `blind_test.py`。「不像我」反饋路由是 handoff 列的 TODO。
- **預期發展**：「像不像我」缺乏乾淨 ground truth——本人評分有偏誤、他人評分需要夠熟的他人。「不像我」是低解析度訊號，使用者說得出「怪」說不出「哪個維度怪」。
- **主要風險**：① 無 ground truth ② blind test 過關 ≠ 實際使用準確 ③ 反饋→8 維度的訊號歸因很難。
- **完成判準**：「像不像我」這個訊號**端到端跑出來過至少一次**（這就是 §2.1 主幹的終點）。

### S6 — 部署 / 當代理人用

- **現況**：已確認有 responder skeleton（`src/virtualme/responder/`），可讀 persona markdown 並生成回覆；但 prompt 目前偏 HR/HRBP demo，不是通用 VirtualMe agent runtime。
- **預期發展**：persona 一旦對外行動 → 究責、揭露（對方知不知道在跟 twin 講話）、BOUNDARIES.md 當安全層夠不夠、長對話中 agent 漂離 persona。
- **主要風險**：① twin 講出本人不認同的話 → 名譽/關係 ② BOUNDARIES 是一份 markdown，擋不擋得住越界行為 ③ persona 可攜 → 任何人拿到檔案就能跑「你」。
- **完成判準**：先定義清楚「twin 拿來幹嘛」。在這之前 S6 不展開（見 §4 繞路陷阱）。

### S7 — 維護 / 漂移 / 生命週期

- **現況**：「重頭開始萃取」指令（全清重來）、`week_progression.py`。
- **預期發展**：人會變，twin 會過期。「全清重來」浪費 8 週有效資料；「增量更新」會累積錯誤。預期需要版本化 persona + 漂移偵測。
- **主要風險**：① 無漂移訊號，除非本人察覺 ② 全 reset vs 增量更新的兩難 ③ 重大生命事件（失業/離婚/重病）讓人不連續改變，twin 看不到。
- **完成判準**：twin 有版本、有「該重訪了」的觸發條件。

### X — 橫切：隱私 / 安全 / 身分倫理 / 法務 / 心理 / IP

- **現況**：`specs/05` 已涵蓋 PII / boundaries。
- **主要風險**：
  - **第三方資料**：訪談會點名沒同意的第三人（這次訪談就出現恭一/哈路基/Mimi）。
  - **法務**：台灣 PDPA / 歐盟 GDPR 對「一個人的人格模型」的處置、被遺忘權。
  - **開源雙用**：別人 fork 來建「非自願對象」的 twin（前任、老闆）。
  - **心理**：面對自己的 twin 的恐怖谷；grief-tech 鄰接（有人會想用此法建逝者 twin）。
- **完成判準**：橫切不是一個「階段」，是每個階段都要過的篩。S0–S7 任一階段的設計都要回答對應的 X 風險。

---

## 4. 繞路陷阱清單（看到就停，回 §2 對照）

1. **在端到端迴路跑通前加深題庫** — 64 題 → 120 題、8 領域 → 16 領域。最高頻陷阱，§1.4 已在邊緣。
2. **為未驗證的引擎做基礎建設** — dashboard、多語系、router、效能優化。引擎還沒證明能萃到人，這些都是早做。
3. **完美主義訪談體驗** — 修不阻斷迴路的體驗細節（措辭、emoji、招呼語氣），當成進度。
4. **S6 在「twin 拿來幹嘛」沒定義前展開** — 沒有目標就設計部署 = 一定繞路。
5. **scout 調查自我膨脹** — §6 的調查若變成「研究 30 篇論文」而不是「回答阻擋主幹的具體問題」。
6. **把 plumbing bug 修復當主幹進度** — bug 要修（它阻斷迴路），但修完是「回到起跑線」不是「往前」。
7. **過度治理** — 為小決策跑完整 Council。medium 以下直接做。
8. **單模型保真未證明就做 cross-model 適配** — 「同一份 persona 在 Claude/GPT/Gemini/Grok
   各自走鐘」是真問題，但屬 S4/S6 後期。在「persona 連一個模型都還沒證明像本人」前去蓋
   Model Adapter Layer / Fidelity Benchmark System = 為未驗證的引擎蓋中介架構（陷阱 2 的變種，
   且反四層北極星「不做炫技 Router」）。外部策略報告把它捧成「大魔王/護城河」——正因為它
   聽起來夠大，最容易被拿來正當化離開主幹。

---

## 5. 定期 Review 機制（L4 友善，不做 dashboard）

### 5.1 每個 VirtualMe session 開場：Trunk Check（30 秒）

Claude 在每個動到 VirtualMe 的 session 開場，輸出三行：

```
TRUNK CHECK
1. 上一段工作推進了哪個階段的「完成判準」？還是 §4 的繞路？
2. 我們現在宣稱在哪個階段——那個階段的薄切片打通了嗎？
3. 此刻有沒有正在踩 §4 任何一條陷阱？
```

Maki 掃一眼即可，不對就喊停。

### 5.2 階段轉換時：深 review

當宣稱某階段「完成判準」達成、要進下一階段前，停下來確認：
判準是不是真的端到端驗證過，還是只是「程式碼寫完了」。

### 5.3 月度：更新本檔

重讀 §1.4「現在站在哪」，更新它；重排 §4 繞路陷阱的當前風險；
檢查 §3 各階段「現況」與「預期發展」的落差——落差大代表預測錯了，要修正預期。

> 可選：用 `/loop` 或排程做月度提醒。但**不要**做需要盯的儀表板（反 L4）。

---

## 6. 待調查清單 → 分批給 ChatGPT / Perplexity Max / SuperGrok

這些是「阻擋主幹推進的具體未知」。每個 scout 依守備範圍分批。
**原則**：調查是為了解鎖主幹，不是為了寫研究報告（§4 陷阱 5）。

scout 守備範圍：
- **Perplexity Max** — 有引用的既定知識：學術方法論、心理計量、法規。
- **ChatGPT** — 結構化推理 + 設計空間比較 + 競品拆解 + 評估框架設計。
- **SuperGrok** — 即時 X/社群：正在發生的競品、輿論、近期事件。

---

### ── 以下整段貼給 ChatGPT ──

**背景**：VirtualMe 是開源專案，用 8 週訪談把一個人萃取成 AI 代理人，產出使用者自己擁有的
markdown 人格檔（SOUL / VOICE / BOUNDARIES）。我需要結構化推理與設計空間比較，請逐題回答。

1. **留存設計**：自我導向、長達 8 週、無教練督促的自我提升型程式，完成率通常多低？
   有哪些「不靠真人督促」的留存機制被驗證有效？（VirtualMe 刻意拿掉了課程的教練層。）
2. **persona 表徵的設計空間**：要讓 LLM 重現一個特定的人，「markdown 人格 prompt」 vs
   「RAG over 錨點」 vs「fine-tune」 vs 混合，各自在**保真度 / 成本 / 漂移 / 可攜性**上的取捨？
3. **回歸通用基線**：LLM 拿到 persona prompt 後傾向回到「通用助理」語氣、磨平獨特性。
   有哪些已知的對抗技巧？
4. **無 ground truth 的驗證**：在沒有乾淨 ground truth 的前提下，怎麼設計一套
   「twin 像不像本人」的評估框架？
5. **competitor 拆解**：Delphi、Personal AI、character/clone-yourself 類產品，
   它們的 onboarding、persona 建構方式、商業模式各是什麼？哪裡做得好、哪裡踩雷？
6. **S6 失效模式**：當一個 persona agent 開始「代表本人」對外行動，列出主要失效模式
   （究責、揭露、邊界執行），以及對應的設計緩解。

---

### ── 以下整段貼給 Perplexity Max ──

**背景**：同上。我需要**有學術/專業文獻引用**的答案，請逐題附來源。

1. **自我報告效度**：人描述「自己會怎麼做」與「實際行為」的落差（espoused vs enacted），
   心理學文獻怎麼量化？訪談設計上有哪些已驗證的修正手法？
2. **矛盾與一致性**：人格研究如何處理「同一個人在不同時間/情境給出矛盾自述」？
   建模時該「解決矛盾」還是「保留矛盾」？
3. **persona 保真度的量測**：學術上怎麼測「一個 AI 模仿特定個人」的保真度 / 建構效度？
   有沒有既成的 LLM-persona 評估方法或 benchmark？
4. **法規**：台灣 PDPA 與歐盟 GDPR，如何處置「一個個人的人格/行為模型」這類衍生資料？
   被遺忘權是否及於「模型」？訪談中出現的**第三人**（未同意）資料如何合規處理？
5. **心理影響**：「與自己的數位分身互動」「為逝者建分身（grief tech）」的已知心理影響研究？
6. **[偏見查證]** 質性訪談方法上，如何區分受訪者「逃進哲學/宿命論來迴避問題」與「他的
   哲學觀本身就是真實答案」？有沒有可操作的判準？（直接影響 STG-036 的「高度偵測器」會
   不會誤殺真實特質——目前 Claude 判定「命運自有安排」是 deflection，此判定待查證。）

> 註：訪談**技術**（追問、停題、具體記憶 elicitation）已在 STG-036 的 `max-questions.md`，此處不重複。

---

### ── 以下整段貼給 SuperGrok ──

**背景**：同上。我需要**即時的 X / 社群情報**——正在發生的事，不是定型的知識。

1. 「打造你的 AI 分身 / clone yourself」這類 $3–5k 課程，X 上現在誰在賣？
   學員的真實評價、有沒有 backlash？
2. 近 3–6 個月，digital twin / personal AI / AI persona 類產品有哪些發布、倒閉、
   爆紅或翻車事件？
3. 一般人對「做一個自己的 AI 分身」的情緒光譜——興奮 vs 毛骨悚然？grief-tech（逝者分身）
   的討論氛圍如何？
4. X / GitHub 上現在正在紅的開源「self twin / persona」專案有哪些？（潛在競品或可借鑑）
5. 近期有沒有 persona-AI 講出有害內容、或「非自願 twin」的爭議事件？
6. **[偏見查證]** 現有 digital twin / persona AI 產品，是把「跨模型可攜性 / cross-model
   fidelity」當**早期**核心去設計，還是**後期**才補？有沒有人把它當賣點/護城河、真的做出來？
   （VirtualMe 內部有一派——由 Claude 提出——認為它是後期問題，想用市場實況檢驗這個判斷。）

---

## 7. Agent ↔ 階段路由（誰在哪一棒，跨 agent / 跨 session 無縫接軌）

> 目的：接手時不用重新決定「這該誰做」。路由依據是**守備範圍**（`rules/agent-routing-default.md`），
> 不是性格、不是感覺。

| 工作類型 | 主責 agent | 主要出現在 |
|---|---|---|
| 架構 / 設計 / 品質裁決 / 方向把關 | Claude（Architect/Judge） | 全階段，尤其 S4 / S5 |
| 寫 code / 修 bug / 重構 / 測試 | Codex（Engineer） | S1–S7 實作 |
| 跨檔 code 分析 / 多方案技術比較 | Gemini（Analyst） | S3 / S4 / S6 |
| 學術方法論 / 心理計量 / 法規（要引用） | Perplexity Max（Scout-1） | S2 / S3 / S5 / X |
| 設計空間推理 / 競品拆解 / 評估框架 | ChatGPT（Scout，推理型） | S1 / S4 / S5 / S6 |
| 即時競品 / 輿論 / 近期事件 | SuperGrok（Scout-2） | S0 / X / 競品掃描 |
| 隱私資料批次 / 逐字稿本地預處理 | gemma4（Local Brain） | X / 訪談逐字稿前處理 |
| ratify / 風險裁量 / 定義「twin 拿來幹嘛」 | Maki（Chair） | 每個階段關卡 |

### 接手 SOP（任何 agent / 任何新 session）

1. **讀 §0 接續錨點** — 知道現在在哪個階段、誰在做什麼、下一步是什麼。
2. **跑 §5.1 Trunk Check** — 確認接下來要做的事在主幹上，不是 §4 繞路。
3. **依上表認領那一棒** — 多 agent 協作由 Maki 人類中繼，採 copy/paste 問答，不要求其他
   agent 讀寫本機檔案，也不使用 CLI File I/O 來協調 agent。若已有外部 briefing markdown，
   Codex/Claude 可讀作參考，但新的委派預設走對話中繼。
4. **session 結束前** — 回填 §0、必要時更新 §3 現況 / §1.4，並寫 memhall。

### 三個接續基座（無縫接軌靠這三個，不靠記憶）

| 基座 | 角色 |
|---|---|
| 本檔 `docs/TRUNK.md` §0 | 「現在在哪、下一步」的單一事實來源 |
| Maki copy/paste 中繼 | 跨 agent 的 briefing / answer 交接；避免 agent 自行透過 CLI/File I/O 協調 |
| memhall（`project` namespace） | 跨 session 長期記憶，entry 內容指回本檔 |

> 對話階段（分析 → briefing → 委派 → 驗證 → ratify）的接軌：
> repo 事實落在本檔與 specs；跨 agent 意見由 Maki 貼入目前對話，由主線 agent 收斂。
> 不再把 agent-to-agent file handoff 當成必要流程。

## 8. Codex Dissent 結論 → 接下來實作路標

2026-05-16 Codex 重新讀 `docs/TRUNK.md`、`specs/09`、`specs/10` 與現有 code 後，給出以下工程路標。

### 8.1 Reposition 的採納邊界

- 採納：VirtualMe 的 north star 是「像我做選擇」，不是只像我講話。
- 限制：`Personality Infrastructure` 是長期定位，不是近期 build scope。
- 近期產品承諾應維持為：用訪談產出可驗證、可修正、可攜帶的 persona archive。

### 8.2 下一個實作順序

1. **Snapshot 薄切片**
   - 從現有 anchors / triples 產出 SOUL-lite hypothesis。
   - 每條結論要附 provenance、confidence、以及「需要再訪談」標記。
   - 不能宣稱 30 分鐘就準，只能宣稱產出可驗證草稿。
2. **Mini Blind Test**
   - 用 SOUL-lite / VOICE-lite 產出少量候選回覆。
   - 讓本人做「哪個像我」或「這不像我」標記。
   - 把結果回寫成下一輪訪談 TODO，而不是直接當最終評分。
3. **不像我 Feedback Routing**
   - 使用者說「這不像我」時，要映射到 dimension / anchor / decision target。
   - 這是主幹，不是 UX 附屬功能。
4. **v2 Altitude + Decision Targets**
   - 在 v2 schema / selector 中補 `decision_targets` 與 answer altitude。
   - aphorism altitude 不能直接成為 anchor，但也不能直接丟棄；要標成 candidate 待驗證。
5. **Feature-flagged v2**
   - `VIRTUALME_INTERVIEW_ENGINE=v1|v2`。
   - v1 保持 production default；v2 只在 Snapshot / staging dogfood 成功後切。

### 8.3 明確暫緩

- 不做 cross-model adapter layer。
- 不做 fidelity benchmark system 的完整版本。
- 不擴題庫到 120 題。
- 不把 Decision Style / Contradiction 做成獨立大子系統；先作為現有訪談與萃取 pipeline 的 metadata / rule refinement。

### 8.4 工程現況確認

- S4：有 markdown export，沒有 synthesis。
- S6：有 responder skeleton，沒有通用 runtime。
- v2 schema：足夠當第一步資料層，但需補 `decision_targets`、altitude、correction routing metadata。
- STG-036：可在現有 `depth_evaluator.py` / `follow_up.py` / `bot.py` 增量實作；風險主要是 UX，不是工程不可行。

---

> 本檔是活文件。scout 答覆回來後，將結論回填到對應階段的「現況/風險」，並更新 §1.4 與 §0。
