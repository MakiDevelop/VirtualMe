# VirtualMe 客戶自架 Operator Runbook

目標：由未參與開發的 operator 在 60 分鐘內，於自己的電腦完成安裝、一次本機 smoke、LINE 一個 session 與 persona zip 匯出。完整逐字稿只持久化在 operator 指定的本機 SQLite，不會上傳到 VirtualMe 平台；但每則訊息生成回覆時仍會送往 Anthropic API，BYOK 只是改用受訪者的 key，不是本地推論。

## 0–10 分鐘：前置準備

- Python 3.11 以上：`python3 --version`
- uv：`uv --version`
- git：`git --version`
- LINE Developers 帳號與一個 Messaging API channel
- Anthropic API key。即使開 BYOK，目前 `virtualme.main` 啟動時仍要求 `ANTHROPIC_API_KEY`；不能只留空。
- ngrok 帳號與 agent CLI：`ngrok version`

不要在 production、共用電腦或真實受訪者資料上做第一次演練。先用測試 LINE 帳號；不要把 `.env`、SQLite、keys、persona 或 zip 加進 git。

## 10–20 分鐘：clone 與安裝

```bash
git clone https://github.com/MakiDevelop/VirtualMe.git
cd VirtualMe
uv sync
cp .env.example .env
```

`uv sync` 會依 `pyproject.toml` 與 `uv.lock` 建立環境，不需另外 `pip install`。

## 20–30 分鐘：設定 `.env`

先填最小可啟動設定：

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_CHANNEL_SECRET=...
LINE_INTERVIEW_ALLOWLIST=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OWNER_LINE_USER_ID=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
CRISIS_ALERT_LINE_USER_ID=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPERATOR_DISPLAY_NAME=你的組織或 operator 名稱
DATABASE_URL=sqlite:///./data/virtualme.db
VIRTUALME_BYOK_ENABLED=false
VIRTUALME_BYOK_KEYS_DIR=./data/keys
VIRTUALME_PERSONA_EXPORT_DIR=./data/personas
VIRTUALME_SNAPSHOT_EXPORT_DIR=./exports
```

| 變數 | 現有程式行為 |
|---|---|
| `LINE_INTERVIEW_ALLOWLIST` | 逗號分隔 LINE user id。新帳號不在清單時收到「封閉測試」固定回覆；已有 session 的帳號仍可續訪。空值不是開放模式。 |
| `OWNER_LINE_USER_ID` | owner 會自動納入 allowlist，也用於既有 owner-only 功能。 |
| `CRISIS_ALERT_LINE_USER_ID` | crisis gate 觸發時的最小 metadata 告警收件者；不含危機原句。未設定時仍會鎖定與回覆受訪者，只是不送 operator alert。 |
| `OPERATOR_DISPLAY_NAME` | 插入 consent 文案的 operator 名稱；不得填 Maki 或 VirtualMe 平台，除非那確實是資料控制者。 |
| `VIRTUALME_BYOK_KEYS_DIR` | `<sha256>.key` 與版本化 `<sha256>.consent`；key 檔不是逐字稿，但屬秘密。 |
| `VIRTUALME_PERSONA_EXPORT_DIR` | persona markdown、local-only git 與 zip。內容是衍生人格資料，仍須視為敏感資料。 |
| `DATABASE_URL` | 目前只支援 `sqlite:///...`；`turns` 與 `redactions.original` 在這個 SQLite。 |
| `REASONER_PROMPT_FILE` | 選用的本機 prompt 檔；只有 `REASONING_TURN_ENABLED=true` 且 id 在 `REASONING_TEST_USER_IDS` 時使用。路徑不存在會在該路徑首次執行時失敗。 |
| 題庫路徑 | 現在固定由 `src/virtualme/data/question-pool.yaml` 的 package resource 載入，沒有環境變數可換路徑。若客戶版另有 private policy plugin，接法目前需確認，不要自行杜撰 env 名稱。 |

BYOK 模式另設：

```dotenv
VIRTUALME_BYOK_ENABLED=true
```

此時 consent 後，受訪者需在 LINE 貼自己的 `sk-ant-...` key；訪談 LLM calls 改用該 key。operator 只能 revoke/replace，不能由 CLI 讀回 key。

## 30–35 分鐘：初始化與本機 smoke

`scripts/init_db.py` 接收檔案路徑，不讀 `DATABASE_URL`。若你改了 DB 位置，兩處必須指向同一檔案。

```bash
uv run python scripts/init_db.py --path ./data/virtualme.db
uv run python scripts/smoke_local.py
```

第二行不需要 LINE、不呼叫網路 LLM，使用暫存 DB/keys/export，依序驗證 consent → 一題 → crisis → 解鎖 → export → forget dry-run。成功只印：

```text
PASS local consent/interview/crisis/resume/export/forget-dry-run
```

## 35–45 分鐘：啟動與 ngrok

終端機 A：

```bash
uv run uvicorn virtualme.main:app --host 127.0.0.1 --port 8000
```

另一個終端機先確認 app 名稱與 health endpoint 正確：

```bash
curl http://127.0.0.1:8000/healthz
```

預期收到含 `"ok":"true"` 的 JSON。終端機 B 將本機 port 暫時曝露成 HTTPS：

```bash
ngrok config add-authtoken <你的-ngrok-authtoken>
ngrok http 8000
```

記下 ngrok 顯示的 `https://...ngrok...` URL。此 URL 只適合開發驗收，agent 停止或 free URL 改變後要重設 LINE webhook。命令格式可對照 [ngrok 官方 CLI 文件](https://ngrok.com/docs/agent/cli)。

## 45–50 分鐘：LINE Developers Console

1. 打開 provider 下的 Messaging API channel，從 Messaging API 分頁取得 Channel secret 與 channel access token，填回 `.env` 後重啟 uvicorn。
2. Webhook URL 填 `https://<ngrok-host>/webhook/line`，不是 `/` 或 `/healthz`。
3. 按 `Verify`，成功後打開 `Use webhook`。LINE 的空 events 驗證請求應收到 HTTP 200。
4. 測試時關閉 LINE Official Account Manager 的 greeting／auto-reply，避免同一訊息出現兩份回覆。
5. 用 QR code 加 bot 好友。

LINE 要求 webhook 使用受信任的 HTTPS 憑證，並建議在 Console Verify 後啟用 webhook；見 [LINE 官方建置步驟](https://developers.line.biz/en/docs/messaging-api/building-bot/)與 [webhook 驗證說明](https://developers.line.biz/en/docs/messaging-api/verify-webhook-url/)。程式已用 LINE SDK 在處理前驗證 `x-line-signature`。

## 50–60 分鐘：驗收清單

所有 `<id>` 都是命令輸入，不會在預設輸出回顯；只有明確加 `--show-id` 才顯示原 id。

- [ ] 用不在 allowlist、且 DB 無既有 session 的陌生帳號傳訊：收到 `VirtualMe 目前為封閉測試, 尚未對外開放。`，沒有建立 session。
- [ ] allowlist 帳號先傳「開始」：收到完整 consent 文案，尚未建立 turn。
- [ ] 完整回覆 `我已滿18歲，同意開始`：收到「已記錄同意」與第一題；同意本身不寫入 turn。
- [ ] 用測試帳號送 `我最近一直想死`：收到程式中的 `CRISIS_REPLY` 固定資源轉介文案，且下列 `crisis_locked` 為 `true`：

  ```bash
  uv run python -m virtualme.operator status <id>
  ```

- [ ] 回覆 `繼續訪談`：收到解鎖固定文案；再跑 status，`crisis_locked` 為 `false`。解鎖句不寫入 turn。
- [ ] 匯出 zip；輸出只有實際 zip path 與檔案數，預設 path 使用 sha8 目錄：

  ```bash
  uv run python -m virtualme.operator export <id>
  ```

- [ ] forget dry-run 只列各資料面計數，不刪除：

  ```bash
  uv run python -m virtualme.operator forget <id> --dry-run
  ```

## 日常 operator 命令

```bash
uv run python -m virtualme.operator list
uv run python -m virtualme.operator status <id>
uv run python -m virtualme.operator pause <id>
uv run python -m virtualme.operator resume <id>
uv run python -m virtualme.operator revoke <id>
uv run python -m virtualme.operator export <id>
uv run python -m virtualme.operator forget <id> --dry-run
uv run python -m virtualme.operator forget <id> --yes
```

`--json` 可放在 command 前或後，供監控程式解析；`--show-id` 只應在確實需要核對原 id、且終端輸出不會被分享或長期保存時使用。沒有任何 dump 對話命令。`forget --yes` 是不可逆 hard delete；先跑 dry-run，依組織授權流程確認後才執行。

## 資料位置對照

完整刪除範圍與已知外部面以 [`docs/retention-map.md`](retention-map.md) 為準。

| 位置 | 是否有逐字稿／敏感內容 | 主要內容 |
|---|---|---|
| `DATABASE_URL` 指向的 SQLite | **有** | `turns.content` 是 scrub 後逐字稿；`redactions.original` 保留被替換原文；anchors/triples 是衍生內容。另含 session、crisis 與 download metadata。 |
| `VIRTUALME_BYOK_KEYS_DIR` | 無逐字稿；**有 secret** | hashed filename 的 API key 與 consent metadata。 |
| `VIRTUALME_PERSONA_EXPORT_DIR/<id>/` | 無完整逐字稿；**有敏感衍生內容** | 由 anchors 產生的 markdown、manifest 與 local git history。 |
| `VIRTUALME_PERSONA_EXPORT_DIR/_packages/` | 無完整逐字稿；**有敏感衍生內容** | LINE export 使用原 id 目錄；operator export 預設使用 sha8 目錄。D7 forget 兩者都處理。 |
| `VIRTUALME_PERSONA_EXPORT_DIR/_receipts/` | metadata only | forget receipt：sha256、計數、錯誤與 receipt hash，不含原 id。 |
| `VIRTUALME_SNAPSHOT_EXPORT_DIR` | 無完整逐字稿；**可能有敏感衍生內容** | snapshot artifact。 |
| app/system logs | metadata；可能有原 id | 目前部分 logger 仍寫原始 LINE user id。D7 不清 journald 或其他系統 log。 |
| LINE 與 Anthropic | 本機磁碟外的第三方資料面 | LINE 傳輸訊息；Anthropic 處理每則 prompt。保存與刪除需依實際帳戶方案另外確認。 |

DB、檔案、nested git 不是跨系統 transaction。正式處理刪除要求時，除 app CLI 外，仍要盤點備份、journald、LINE 與 Anthropic 帳戶設定。

## Operator 責任摘要

依 [`specs/05-boundaries-and-pii.md` §10](../specs/05-boundaries-and-pii.md#10-operator-responsibilities)：

- 不得無故閱讀逐字稿；保密義務也適用 operator。
- 每 2 週最多抽查 15 分鐘，目的限於 bot 行為與 drift 品質查核。
- 24 小時內履行刪除要求，且不得把本地 receipt 說成 LINE／Anthropic／備份也已刪除。
- 只能按 consent 已揭露目的使用資料；替別人營運的注意義務高於自用。
- crisis gate 不可關閉，也不可把固定停機文案改成繼續追問。

無法承諾上述責任時，不要替他人營運 VirtualMe。
