# VirtualMe 資料保留面對照

本文件描述目前程式可觀察到的資料面與 `python -m virtualme.forget` 的涵蓋範圍，不構成保留期限或法規遵循承諾。

## App 管理面

| 資料面 | 位置 | forget 行為 | 刪除後查核 |
|---|---|---|---|
| 訪談、推論與營運 metadata | SQLite：`sessions`、`turns`、`redactions`、`anchors`、`persona_triples`、`question_state`、`blind_tests`、`subjects`、`checklist_items`、`transport_events`、`persona_download_tokens`、`persona_download_logs`、`crisis_events` | 同一 transaction 依 interviewee 刪除；`--keep-crisis-stub` 會刻意留下 crisis metadata，因而不會取得全零證明 | 動態列舉所有 app table 的 TEXT 欄位，搜尋原 id 與其 sha256 |
| BYOK key 與 consent | `VIRTUALME_BYOK_KEYS_DIR/<sha256>.key`、`<sha256>.consent` | 驗證路徑仍在 keys root 後刪除 | 遞迴掃描檔名與內容 |
| Persona markdown | `VIRTUALME_PERSONA_EXPORT_DIR/<id>/` | 先處理巢狀 git 歷史，再驗證路徑並刪除 | 遞迴掃描檔名與內容 |
| Persona zip | `VIRTUALME_PERSONA_EXPORT_DIR/_packages/<id>/`；operator CLI 預設另用 `_packages/<sha8>/`，避免輸出路徑洩漏原 id | 驗證路徑仍在 `_packages` root 後刪除，兩種目錄都涵蓋 | 隨 persona export root 遞迴掃描 |
| Persona 巢狀 git | `VIRTUALME_PERSONA_EXPORT_DIR/.git/` | 以 sha8 commit 刪除索引路徑，再執行 `filter-branch`、清 backup refs、expire reflog 與 gc；任一步失敗會記入 receipt 並回傳非零 | `git grep` 掃全部 revision 內容；`git log --all -- <id>` 掃歷史路徑 |
| Snapshot | `VIRTUALME_SNAPSHOT_EXPORT_DIR/<id>/` 或 `<sha256>` 命名的直屬檔案／目錄 | 驗證路徑仍在 snapshot root 後刪除 | 遞迴掃描檔名與內容 |
| 刪除證明 | `VIRTUALME_PERSONA_EXPORT_DIR/_receipts/`，或 `--receipt-dir` | 保留 sha256、計數、錯誤與 receipt hash，不保存原 id | `_receipts/` 不納入 identity 掃描，避免無 PII 證明自我命中 |

DB、git、檔案三面無法形成跨系統 transaction。DB 面是全成功或全回滾；git 或檔案面失敗會留在 receipt，且 CLI exit code 為 2。

## 非 app 管理面

| 資料面 | 現況 | 部署 operator 應處理的項目 |
|---|---|---|
| systemd journald / 應用程式 log | `transport/line.py`、`interview/byok.py`、`interview/bot.py`、`export/auto.py` 等 logger 呼叫目前會寫入原始 LINE user id；forget 不修改 journald | 依部署需求設定 journald 的保存上限、輪替與存取權；刪除要求需另行處理既有 log。原始 id 改為 sha8 是 follow-up，本輪未改程式 |
| VPS / volume / SQLite 備份 | 備份是 app 執行環境之外的副本；forget 只操作目前 Settings 指向的 live 路徑 | 盤點實際備份位置，設定可驗證的輪替與到期流程，並把備份還原演練納入刪除查核 |
| LINE 平台訊息紀錄 | LINE 平台保存其傳輸與帳號側紀錄；VirtualMe CLI 無權刪除 | 由 operator 依 LINE 提供的管理介面、合約與文件確認可用的保留／刪除控制 |
| Anthropic API log | 送往 Anthropic API 的請求可能受供應商帳戶設定與條款管理；VirtualMe CLI 無權刪除供應商側紀錄 | 由 operator 依實際帳戶方案與當期供應商文件確認 log／retention 設定；不要以本地 receipt 代表供應商側已刪除 |

部署驗收時，operator 應記錄實際的 DB、keys、persona export、snapshot 與 receipt 絕對路徑，並另列 journald、備份、LINE、Anthropic 四個非 app 管理面的 owner 與查核方式。
