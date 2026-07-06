---
name: warp-oz-monitor
description: "Use after triggering Warp Oz via ask-warp.ps1 to poll run status, send follow-ups, and summarize failures in plain language for Edgar. Uses watch-warp-run.ps1."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [warp, oz, monitor, polling, followup, watch]
    related_skills: [warp-oz-cursor, warp-oz-linear]
---

# Warp Oz Monitor

## Overview

叫 Oz 做事後（`ask-warp.ps1` 或 Linear `@Oz`），用本技能**盯任務跑完**、中途補指令、失敗時用白話回報 Edgar。

```
ask-warp.ps1 → Run ID + session_link
  └─ watch-warp-run.ps1 -RunId <id>     # 等到完成
  └─ watch-warp-run.ps1 -RunId <id> -FollowUp "..."  # 中途 steer
```

## When to Use

- `ask-warp.ps1` 沒加 `-Wait`，但需要知道何時完成
- Oz 開 PR 後，要確認任務狀態再本地驗證
- 任務跑錯方向，要送 follow-up 修正
- 失敗時要把 `status_message` 翻成 Edgar 聽得懂的中文

## Prerequisites

- `WARP_API_KEY` 已設定（同 `warp-oz-cursor`）
- 手上有 **Run ID**（`ask-warp.ps1` 輸出）或 session link 對應的 run

## Procedure

### 1. 取得 Run ID

`ask-warp.ps1` 成功後會印：

```text
Run ID：xxxxxxxx
查看進度：https://...
```

記下 Run ID。

### 2. 監看到完成

```powershell
cd V:\projects\linear-orchestrator
.\scripts\watch-warp-run.ps1 -RunId "<run_id>"
```

預設每 15 秒查一次，直到 `SUCCEEDED`、`FAILED` 或 `CANCELLED`。

自訂間隔：

```powershell
cd V:\projects\linear-orchestrator
.\scripts\watch-warp-run.ps1 -RunId "<run_id>" -IntervalSec 30
```

### 3. 中途送 follow-up

任務還在跑（`INPROGRESS`）時可 steer：

```powershell
cd V:\projects\linear-orchestrator
.\scripts\watch-warp-run.ps1 -RunId "<run_id>" -FollowUp "請改用 pnpm 不要用 npm，並在 PR 描述加測試步驟"
```

只送 follow-up、不等待結束：送完即結束腳本（不加額外輪詢時需分兩次呼叫；若同時傳 `-FollowUp` 腳本會先送 follow-up 再進入監看循環）。

### 4. 成功時回報 Edgar

白話範本：

> Oz 做完了。點這裡看詳情：{session_link}  
> 若有 PR，我幫你確認一下連結。

### 5. 失敗時回報 Edgar

腳本會輸出白話摘要，直接貼給 Edgar，例如：

> Warp 任務沒有成功完成。狀態：失敗。原因：{status_message}  
> 詳情連結：{session_link}

Agent 可建議：改 prompt 重叫 `ask-warp.ps1`，或 Linear 重新 `@Oz`。

### 6. JSON 輸出（給腳本串接）

```powershell
cd V:\projects\linear-orchestrator
.\scripts\watch-warp-run.ps1 -RunId "<run_id>" -Json
```

回傳：`run_id`, `state`, `session_link`, `succeeded`, `summary`。

## Typical Workflow

1. `ask-warp.ps1` 送任務（背景跑）
2. 立刻貼 session_link 給 Edgar
3. 需要收尾時 → `watch-warp-run.ps1 -RunId ...`
4. 成功 → 驗 PR / 本地 smoke test
5. 失敗 → 白話摘要 + 建議下一步

## API Reference (internal)

| 操作 | API |
|------|-----|
| 查狀態 | `GET /api/v1/agent/runs/{runId}` |
| Follow-up | `POST /api/v1/agent/runs/{runId}/followups` body `{ "message": "..." }` |

腳本已封裝，Agent 優先用 `watch-warp-run.ps1`，不要手寫 curl。

## Verification

```powershell
cd V:\projects\linear-orchestrator
$r = .\scripts\ask-warp.ps1 -Prompt "讀 README 一句話摘要"
# 從輸出複製 Run ID
.\scripts\watch-warp-run.ps1 -RunId "<上一步的 Run ID>"
```

## Common Pitfalls

1. **沒 Run ID 就監看** → 先跑 `ask-warp.ps1`
2. **任務已結束才 follow-up** → follow-up 主要給 `INPROGRESS`；已結束應開新任務
3. **失敗只貼英文 status_message** → 用腳本輸出的 `summary` 白話版
4. **用 warp.exe CLI 查狀態** → 用本腳本或 API

## Related Paths

| 路徑 | 用途 |
|------|------|
| `V:\projects\linear-orchestrator\scripts\watch-warp-run.ps1` | 監看與 follow-up |
| `V:\projects\linear-orchestrator\scripts\ask-warp.ps1` | 建立任務（`-Wait` 為內建簡版監看） |
