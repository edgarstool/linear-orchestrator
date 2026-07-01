---
name: daily-standup
description: 產生每日 standup 報告，彙整 Linear 任務進度、Git commit log 與 mem0 歷史記憶，輸出結構化的「昨日完成 / 今日計畫 / Blockers」。當使用者提到 standup、每日站會、進度回報、daily update、「我昨天做了什麼 / 今天要做什麼」、「幫我整理進度」、或想把跨來源（Linear + git + 記憶）的近況彙整成一份報告時，主動使用這個 skill；即使使用者沒有講出「standup」這個字，只要意圖是彙整近期工作進度就套用。
---

# daily-standup

自動彙整三個來源，產出結構化 standup 報告：

1. **Linear** — 指派給我的任務，依 workflow state 分類（完成 / 進行中 / 被卡住）。
2. **Git** — 指定窗口內的 commit log。
3. **mem0** — 語意搜尋歷史記憶，補上跨天的脈絡與 blocker 記憶。

報告永遠使用固定三段結構：**✅ 昨日完成 / 🎯 今日計畫 / 🚧 Blockers**，另附 mem0 記憶脈絡與 git commits 明細。

## 什麼時候用

- 使用者說「standup」「站會」「daily」「進度回報」「幫我整理昨天/今天」。
- 想把 Linear + git + 記憶湊成一份可貼回 Linear / Obsidian 的近況。
- 排程情境（例如每天早上自動產生）。

## 怎麼執行

核心邏輯都在 `scripts/standup.py`，零額外依賴（只用 Python 標準庫）。直接跑：

```bash
python scripts/standup.py
```

常用參數：

- `--window-hours N`：回溯窗口，預設 24。跨週末補班時可拉到 72。
- `--format json`：輸出機器可讀 JSON（給下游程式用），預設 `markdown`。
- `--repo <path>`：指定 git repo，預設當前目錄。
- `--author <name>`：只計算某作者的 commit。
- `--no-git` / `--no-linear` / `--no-mem0`：關掉個別來源。
- `--output <file>`：寫檔而非印到 stdout。
- `--post-to-issue <issueId>`：把報告當 comment 貼回某 Linear issue。
- `--mem0-query "..."`：自訂 mem0 語意搜尋字串。

## 前置環境變數

只提供有 token 的來源會被查詢，缺的會在報告末尾標註「資料來源備註」而不會讓整份報告失敗。

- `LINEAR_API_KEY`：Linear personal API key（`lin_api_...`），抓 `viewer.assignedIssues`。
- `MEM0_API_KEY`：mem0 platform key（可選）。
- `MEM0_USER_ID`：mem0 查詢的 peer/user id（可選，預設 `edgar`）。
- `MEM0_BASE_URL`：mem0 API base（可選，預設 `https://api.mem0.ai`）。

不要在 prompt 或程式碼裡貼出這些 secret 值；假設它們已由 Doppler / 1Password / `~/.hermes/.env` 注入環境。

## 分類邏輯（重要）

依 Linear workflow state 的 `type` 欄位分類，而非 state 名稱（名稱因團隊而異）：

- **昨日完成**：`type` 為 `completed` 或 `canceled`，且 `completedAt`（或 `updatedAt`）落在窗口內。
- **今日計畫**：`type` 為 `started`（進行中）或 `unstarted`（待辦）；`started` 排在前面。
- **Blockers**：上述進行中/待辦任務中，帶有 `block` 相關 label，或被尚未完成的其他 issue 透過 `blocks` 關係卡住。

## 報告結構

固定使用這個模板（`render_markdown` 已實作，勿隨意改動段落順序）：

```
# 📋 Daily Standup — YYYY-MM-DD
_窗口：... · 產生者：..._

## ✅ 昨日完成
- `EDG-12` 修好 webhook 埠衝突 [Done]

## 🎯 今日計畫
- `EDG-15` 建立 daily-standup skill [In Progress]

## 🚧 Blockers
- `EDG-20` 等 OAuth secret [Todo] — 被 EDG-18 卡住

## 🧠 記憶脈絡（mem0，N）
- ...

## 🔨 Git commits（N）
- `abc1234` feat: ... — 德德
```

## 修改與擴充

- 要調整報告版型：改 `render_markdown` / `render_json`。
- 要換資料來源或加欄位：改對應的 `collect_*` 與 `classify_issues`。
- 純函式（`parse_git_log`、`classify_issues`、`render_*`）都有 unit test，改動後跑 `pytest tests/test_standup.py`。

更多資料來源與 API 細節見 `references/data-sources.md`。
