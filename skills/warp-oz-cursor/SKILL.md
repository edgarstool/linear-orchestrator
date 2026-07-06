---
name: warp-oz-cursor
description: "Use when Cursor or Hermes must delegate code changes in V:\\projects to Warp Oz via ask-warp.ps1. Covers mandatory Warp-first workflow, -Project selection (linear/deploy/general), -Wait, session_link handoff, and WARP_API_KEY setup."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [warp, oz, cursor, ask-warp, cloud-agent, automation]
    related_skills: [warp-oz-router, warp-oz-linear, warp-oz-monitor, warp-oz-deploy]
---

# Warp Oz × Cursor

## Overview

在 `V:\projects\` 底下要**改程式、開 PR、重構、修 bug、寫測試**時，Agent **必須先叫 Warp Oz**，不要自己在 Cursor 裡大改同一塊。

本機用 [`ask-warp.ps1`](V:\projects\linear-orchestrator\scripts\ask-warp.ps1) 送任務；Oz 在雲端 Docker 環境 clone repo、改 code、開 PR。

```
Cursor / Hermes
  └─ ask-warp.ps1 -Prompt "白話任務" -Project linear|deploy|general
       └─ Warp API POST /agent/run
            └─ Oz 雲端執行 → session_link + 可能 PR
```

## When to Call Warp (Mandatory)

在 `V:\projects\` 任一 repo，任務包含以下**任一項**就必須先叫 Warp：

- 新增 / 修改 / 刪除原始碼或設定檔
- 重構、修 bug、加功能、寫測試
- 開 branch、commit、push、開 PR（若 Oz 可代為完成）

## When NOT to Call Warp

- 純問答、解釋架構、讀檔說明
- 只查 log / 診斷、不改檔
- Edgar 明確說「這張 Hermes 就好」或「不要叫 Warp」
- 僅改 `G:\AgentKB`、`G:\Obsidian` 筆記（非 `V:\projects` code）

## Prerequisites

| 項目 | 檢查方式 |
|------|---------|
| `WARP_API_KEY` | 使用者環境變數；未設定見下方 Procedure |
| Warp 訂閱 | Build+ 方案、credits ≥ 20（integration 用） |
| 腳本路徑 | `V:\projects\linear-orchestrator\scripts\ask-warp.ps1` |

## Procedure

### 1. 確認 API 金鑰（首次或失敗時）

```powershell
cd V:\projects\linear-orchestrator
.\scripts\setup-warp-api.ps1
```

若缺少金鑰：

```powershell
cd V:\projects\linear-orchestrator
.\scripts\setup-warp-api.ps1 -CreateApiKeyIfMissing
```

### 2. 選 `-Project` 環境

| `-Project` | Environment | 用途 |
|------------|-------------|------|
| `linear`（預設） | `edgar-linear-dev` | linear-orchestrator、Linear 相關 Python 專案 |
| `deploy` | `deploy-pilot` | 部署上線（見 `warp-oz-deploy` skill） |
| `general` | `new world` | 其他 Edgars-tool repos（Node 等） |

不確定時用 `warp-oz-router` skill 決策表。

### 3. 送出任務

```powershell
cd V:\projects\linear-orchestrator
.\scripts\ask-warp.ps1 -Prompt "<白話任務：repo、要做什麼、驗收標準>" -Project general
```

**Prompt 必須包含：**
- 目標 repo 路徑或 GitHub `owner/repo`
- 要做什麼（白話）
- 驗收標準（怎樣算做完）

範例：

```powershell
cd V:\projects\linear-orchestrator
.\scripts\ask-warp.ps1 -Project general -Prompt "在 Edgars-tool/hermes-inn-UI 修登入頁按鈕無法點擊的 bug。驗收：按鈕可點、npm test 通過、開 PR 附簡短說明。"
```

### 4. 回報 Edgar

任務送出後**必須**把輸出中的 **session_link** 貼給 Edgar，白話說「Oz 在這裡改，點連結看進度」。

若 Oz 已開 PR，附上 PR URL。

### 5. `-Wait` 何時用

| 情境 | 建議 |
|------|------|
| 背景跑、Edgar 自己點連結看 | 不加 `-Wait`（預設） |
| 需要等完成再本地驗證 / commit | 加 `-Wait` |
| 長時間任務 | 不加 `-Wait`，改用 `watch-warp-run.ps1`（見 `warp-oz-monitor`） |

```powershell
cd V:\projects\linear-orchestrator
.\scripts\ask-warp.ps1 -Wait -Project general -Prompt "..."
```

### 6. Oz 完成後的本地收尾

若 Oz 已開 PR 或有 diff：
- **不要**在 Oz 能做的事上重複大改
- 本地補驗證（test、lint）或收尾小修正即可

## Agent Workflow (Step by Step)

1. 用白話整理任務（repo、動作、驗收）
2. 依 `warp-oz-router` 確認應叫 Warp（不是本地改）
3. 選 `-Project`
4. 執行 `ask-warp.ps1`
5. 貼 `session_link` 給 Edgar
6. 若需盯完成 → `watch-warp-run.ps1` 或 `-Wait`

## Verification

```powershell
cd V:\projects\linear-orchestrator
.\scripts\setup-warp-api.ps1
# 應顯示 API 連線成功、環境列表

.\scripts\ask-warp.ps1 -Prompt "讀 README 並用三句話摘要這個專案"
# 應回 Run ID 與 session_link
```

## Common Pitfalls

1. **跳過 Warp 直接改 code** → 浪費訂閱額度設計初衷；違反 Edgar user rule
2. **`WARP_API_KEY` 未設定** → 跑 `setup-warp-api.ps1 -CreateApiKeyIfMissing`
3. **Prompt 太模糊** → Oz 容易做錯；務必寫 repo + 驗收標準
4. **用 `warp.exe` / `oz` CLI 在 Cursor 終端** → 易卡住；只用 `ask-warp.ps1`
5. **Oz 做完又本地大改同一功能** → 衝突；本地只驗證收尾

## Related Paths

| 路徑 | 用途 |
|------|------|
| `V:\projects\linear-orchestrator\scripts\ask-warp.ps1` | 叫 Warp 主腳本 |
| `V:\projects\linear-orchestrator\scripts\setup-warp-api.ps1` | API 檢查與金鑰 |
| `V:\projects\linear-orchestrator\scripts\watch-warp-run.ps1` | 盯任務狀態 |
| `V:\projects\linear-orchestrator\skills\warp-oz-router\SKILL.md` | Hermes vs Oz 分工 |
