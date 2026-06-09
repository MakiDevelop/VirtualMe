# IDS Trac 專案管理系統使用指南

## 基本資訊

- **網址**: https://trac.chiba.tw
- **登入方式**: Google @91app.com 帳號自動登入
- **用途**: IDS 部門專案管理、任務追蹤

---

## 登入

1. 打開 https://trac.chiba.tw
2. 會自動跳轉到 Google 登入頁面
3. 選擇你的 @91app.com 帳號登入
4. 登入後即可使用所有功能

> 如果遇到 400 錯誤，請用無痕視窗重試，並確認選的是 @91app.com 帳號。

---

## 團隊成員帳號

| 帳號 | 姓名 |
|---|---|
| makichiang | Maki Chiang |
| yoyoliu | Yoyo Liu |
| lewiswang | Lewis Wang |
| ivanlee | Ivan Lee |
| ronchen | Ron Chen |
| brickliao | Brick Liao |
| teresachang | Teresa Chang |

---

## 票的欄位說明

| 欄位 | 說明 | 選項 |
|---|---|---|
| **類型** | 票的性質 | 專案 / 任務 / Bug |
| **優先級** | 重要程度 | P0（最高）→ P4（最低） |
| **產品線（Component）** | 歸屬哪條產品線 | BN Manager / 個人化行銷進階版 / Data Cloud / IDS效率化 / SKA / 訪客標籤系統 / CDMP / 通知中心 |
| **負責人** | 誰負責這張票 | 從下拉選單選 |
| **CC** | 通知對象（票有變動會寄信） | 直接打帳號名，多人用逗號隔開，例如：`yoyoliu, lewiswang` |
| **擋住** | 這張票擋住哪些票 | 填票號，例如 `#3, #5` |
| **被擋住** | 這張票被哪些票擋住 | 填票號 |
| **標籤（Tags）** | 自由標記 | 逗號分隔，例如：`寶雅, 卡關, 資料驗證` |

---

## 票的類型用法

| 類型 | 用在 | 範例 |
|---|---|---|
| **專案** | 母票，代表一個完整專案 | CMoney發票數據導入、寶雅CDMP 2.0 |
| **任務** | 子票，代表專案中的一個環節 | 取得資料源、合約用印、資料驗證 |
| **Bug** | 系統問題需要修復 | Looker 報表數字異常 |

---

## 母子票（擋住/被擋住）

用「擋住」和「被擋住」建立票之間的依賴關係：

**範例**：
- 票 #10「CMoney 合約用印」**被擋住** `#9`（報價單回簽）
- 票 #9「CMoney 報價單回簽」**擋住** `#10`（合約用印）

意思：報價單沒簽完，合約就不能用印。

---

## 常用報表

到 https://trac.chiba.tw/report 查看：

| # | 報表 | 用途 |
|---|---|---|
| 1 | 進行中的票 | 所有未關閉的票 |
| 7 | 我的票 | 只看自己負責的票 |
| 9 | 依產品線 | 按 Component 分組 |
| 10 | 依優先級（P0 最前） | P0 排最前面 |
| 11 | 依負責人 | 每個人手上有什麼 |
| 12 | 我的待辦 | 我負責的進行中票 |
| 13 | 最近更新（7天內） | 過去一週有動的票 |
| 14 | 已完成 | 結案清單 |

---

## 內容格式

票的描述和留言支援 **Markdown** 格式：

```markdown
## 問題描述
資料源需要重新拉取

### 步驟
1. 聯繫 CMoney 取得 API
2. 驗證資料格式
3. 匯入 Looker

**截止日**: 6/12
```

---

## Email 通知

票有變動時，以下人會自動收到通知信（來自 makichiang@91app.com，主旨前綴 `[IDS]`）：

- **負責人**：票的 Owner
- **回報者**：開票的人
- **CC 名單**：被加在 CC 欄位的人

---

## 附件

每張票和每個 Wiki 頁面都可以上傳附件：
- 單檔上限 **50MB**
- 支援所有檔案格式（PDF、Excel、圖片等）

---

## API / MCP（給 Claude 用）

Trac 有 REST API，部署在 **https://trac.chiba.tw/api/**，Claude Code 可以透過 MCP 直接操作：

- `trac_list_tickets` — 列出票
- `trac_create_ticket` — 開票
- `trac_update_ticket` — 更新票
- `trac_close_ticket` — 關票
- `trac_run_report` — 跑報表

設定方式：在 Claude Code 的 `settings.json` 加入 MCP server 設定（找 Maki 拿設定檔）。

---

## 快速連結

- [首頁](https://trac.chiba.tw)
- [開新票](https://trac.chiba.tw/newticket)
- [所有報表](https://trac.chiba.tw/report)
- [時間軸](https://trac.chiba.tw/timeline)
- [Wiki](https://trac.chiba.tw/wiki)
- [REST API](https://trac.chiba.tw/api/)
