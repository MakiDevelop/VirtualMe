# VirtualMe

> 把一個人**萃取**成 AI 代理人——用 8 週訪談，不用填表。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![English](https://img.shields.io/badge/Lang-English-red.svg)](README.en.md)

---

![VirtualMe Concept](diagrams/virtualme-concept.png)

## 為什麼這個 repo 存在

市面上一堆「打造你的 AI 分身」課程在賣 $3,000–$5,000 USD。我看了大綱，他們在賣三件事：

1. 教你怎麼填 SOUL.md / SKILL.md 之類的人格檔案
2. 教你串 Claude / OpenAI API
3. 同儕網絡 + 督促 + 教練回饋

**技術上，這三件事不需要 $4,000。** VirtualMe 是這三件事的 open-source 版本。

順帶兩件事：

- 這不是另一個會在某天 silently update 之後讓你覺得「我的 AI 變成另一個人了」的黑盒子產品——SOUL / VOICE / BOUNDARIES 是你自己的 markdown 檔，每次修改你都看得到、改得回。
- 你的訪談對話**不出你的機器**。沒有後台、沒有人類 moderator review、沒有 cloud sync。`hard delete` 是真的 hard。

## Why now（為什麼是現在做這個）

學術界已經把這條路驗證掉了：Stanford 的 Joon Park 等人 2024-11 發表 [arXiv:2411.10109](https://arxiv.org/abs/2411.10109)，證明 2 小時訪談 + LLM 可達 85% GSS 重答準確度。Joon 本人 2026-02 把這個技術 productionize 成 [Simile](https://siliconangle.com/2026/02/12/ai-digital-twin-startup-simile-raises-100m-funding/)，由 Index Ventures 領投、Fei-Fei Li 與 Andrej Karpathy 背書，融資 **$100M USD**。

Simile 有兩條產品線：
- **B2B**：給企業預測客戶 / 員工行為（已有 CVS Health、Wealthfront、Suntory、Gallup 等客戶）
- **B2C**：[MiniMe](https://minime.simile.ai)，10 分鐘訪談給個人用戶建 AI agent

MiniMe 跟 VirtualMe 是**最直接的競品**。對比：

| | Simile MiniMe | VirtualMe |
|---|---|---|
| 訪談長度 | ~10 分鐘（單次） | 8 週多輪 therapist-style |
| 訪談深度 | 快速 snapshot | R1–R5 五層追問 + 三角校驗 |
| 開源 | ❌ 閉源 | ✅ MIT |
| 驗證機制 | 未公開 | Blind test protocol (Week 5 / Week 8) |
| 數據所有權 | Simile 持有 | 你自己的 markdown 檔 |
| 成本 | 未知（可能捆綁訂閱） | ~$60 一次 + $5/月 |
| 持續演進 | 平台決定 | 你自己 commit / fork |

> **如果你要的是 10 分鐘快速 snapshot 拿去 Simile 用，去 MiniMe。**
> **如果你要的是 8 週深度萃取、檔案自己擁有、隨時可以 fork——VirtualMe。**

兩件事不同方向，不是替代關係。但你應該清楚自己在選哪一條。

開源個人 AI extraction 的生態目前幾乎空白（spec [`07-related-work.md`](specs/07-related-work.md) 有完整盤點：5 個 verified open-source neighbors，沒有一個實作完整 pipeline）。時間窗口很短。

## 核心翻轉：不填表，被訪談

填問卷產出的人格檔案是**表演式**的——大多數人寫的是「我想成為的樣子」而不是「我實際是誰」，結果產出的 AI 代理人講話像 LinkedIn 簡介。

VirtualMe 用 **therapist-style 深度訪談**取代問卷：

- Bot 每次問一題，等你完整回答，**追問 rationale**
- 五條 R1–R5 追問規則：事實 → 模式 → 原則 → 反例 → 三角校驗
- 只有**三角校驗過的原則**（在 ≥3 個不同問題出現過）才寫進 SOUL 錨點
- 行為樣本 / 失敗案例權重高於抽象自陳

## 學術依據

Stanford / Joon Park et al. ([arXiv:2411.10109](https://arxiv.org/abs/2411.10109)) 已證實：**2 小時訪談 + LLM** 可以以 **85% 準確度**重現受訪者的 General Social Survey 答案——比受訪者本人一週後重答還準。

VirtualMe 把這個發現延伸成可上線的 pipeline：
- 訪談分散到 8 週 × 30 分鐘（總共 4–6 小時，遠超 2 小時門檻）
- 同步蒐集語音樣本給 retrieval-augmented 代言用
- Week 5 / Week 8 兩次盲評 gate 擋過擬合

## 8 週後你會拿到什麼

8 個 markdown 檔案（你的 archive）：

| 檔案 | 內容 |
|---|---|
| `SOUL.md` | 身份、價值觀、紅線 |
| `VOICE.md` | 標籤化語氣樣本（retrieval-augmented，不全進 prompt） |
| `SKILL.md` | 領域 know-how |
| `PEOPLE.md` | 關係人物 schema |
| `HISTORY.md` | 人生敘事 |
| `JOURNAL.md` | 事件 log（月更） |
| `BOUNDARIES.md` | 拒答清單 + PII 規則 + persona update protocol |
| `STATE.md` | 近況（月更） |

加上一個可用的 agent endpoint，可以：
- 起草給客戶 / 候選人 / 同事的訊息
- 用你的語氣回覆公開貼文
- 篩選 incoming 訊息
- 永遠是 **draft → 你 review → ship**，不會自動發

## 不能做 / 不會做的事

- ❌ 這不是 chatbot 平台。是「萃取你」的 pipeline，產出檔案後你可以餵給任何 LLM。
- ❌ 不是 fine-tune。是 prompt-layer + retrieval。便宜、快速、可替換。
- ❌ 不是自動代理人。每一則 outgoing 訊息都是 `draft → 人類 review → ship`。
- ❌ 不是課程。沒有教練、沒有同儕、沒有結業證書。讀 spec、fork repo、自己跑。

## 誠實告知的限制

- Prompt-layer persona 在**長對話一致性**和**對抗性輸入**上有結構性上限
- 真正 production-grade 的個人 AI 需要 fine-tune（六位數成本）
- VirtualMe 是「80% 日常場景夠用、不完美」的版本，不是 perfect fidelity
- 高風險決策永遠由人類覆寫，不依賴代理人

## 成本

- 一次性：< $60 USD（Claude API 跑 16 次訪談 session）
- 持續：~$5 USD/月（月更 STATE + 偶爾 inference）

大約是 $4,000 課程的 **1.25%**。

---

## Quick Start

需求：Python 3.11+、Anthropic API key。

```bash
git clone https://github.com/MakiDevelop/VirtualMe.git
cd VirtualMe

# 安裝
pip install -e ".[dev]"

# 設定環境變數
cp .env.example .env
# 編輯 .env，填 ANTHROPIC_API_KEY

# 初始化資料庫
python scripts/init_db.py --path ./data/virtualme.db

# Phase 0：CLI 跑一輪訪談（不接 LINE）
python -m virtualme.cli --interviewee yourself
```

接 LINE / Telegram / 其他 messaging platform → 改 `src/virtualme/transport/`。

---

## 文件結構

```
specs/                          # 完整 spec（讀這裡）
  00-overview.md                # 從這份開始
  01-interview-engine.md        # 訪談引擎、R1-R5、Question Selection
  02-question-pool.md           # 70+ 題分 8 週、領域客製範例
  03-blind-test-protocol.md     # Week 5 / Week 8 盲評流程
  04-tech-stack.md              # FastAPI + SQLite + Claude Opus
  05-boundaries-and-pii.md      # 倫理 / 隱私 / informed consent / 紅線
  06-three-plans.md             # 三種跑法（自跑 / 代跑 / 群組）

src/virtualme/
  config.py                     # Pydantic Settings
  main.py                       # FastAPI app
  cli.py                        # 本機 CLI
  interview/
    bot.py                      # 核心 orchestrator (process_turn)
    depth_evaluator.py          # fact / pattern / principle 分類
    follow_up.py                # R1-R5 decision tree
    question_selector.py        # Question Selection 算法
    anchor_extractor.py         # 從 turn 萃取 anchor
    pii.py                      # 輕量 PII detection
  storage/
    schema.sql                  # SQLite schema
    db.py                       # 資料層
  transport/
    line.py                     # LINE webhook
    cli.py                      # CLI transport
  data/
    question-pool.yaml          # 題庫（agnostic 模板 + 客製範例）

diagrams/
  virtualme-concept.png         # 系統概念圖

tests/unit/                     # 單元測試
scripts/init_db.py              # DB 初始化
```

---

## 三種跑法

| 適合誰 | 你做什麼 | 成本 |
|---|---|---|
| **Plan A 自跑** — 技術人員 | Fork、客製、跑 8 週 | ~$50 API |
| **Plan B 代跑** — 技術人員幫非技術人員跑 | Operator 全包技術；受訪者 8 週聊天 | $50–80 API |
| **Plan C 群組** — 朋友一起跑 | 各自一個 DB；facilitator 協助 | 自訂 |

詳見 [`specs/06-three-plans.md`](specs/06-three-plans.md)。

---

## License

MIT — see [LICENSE](LICENSE)。

---

## 致謝

- Stanford 研究團隊 + Joon Park 等人提供 interview-based agent extraction 學術基礎
- Anthropic 提供 Claude API（也是 VirtualMe 的核心 LLM）
- 所有願意花 8 週讓 bot 訪談自己的人

## 貢獻

issues / PRs welcome。但這個 repo 的 scope 刻意小——歡迎：
- ✅ 翻譯（增加語言版本 README）
- ✅ 領域 question pool 客製範例（Sales / Engineer / PM / Doctor / Teacher / 其他）
- ✅ 新的 messaging transport（Telegram / Discord / Slack / Matrix）
- ✅ Spec 清晰度改善

謝絕：
- ❌ Dashboard / 管理介面（違反設計哲學——不做需要盯著看的東西）
- ❌ 多租戶 SaaS 化（單人 pipeline 才是核心）
- ❌ 自動 fine-tune（prompt-layer 夠用，不必過度工程化）

---

**討論細節：** GitHub issues 或在 [LinkedIn](https://www.linkedin.com/) DM 我。
