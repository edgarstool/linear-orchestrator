---
name: warp-oz-linear
description: "Use when triggering Warp Oz cloud agents from Linear, or when deciding Oz vs local Hermes. Covers Oz CLI (environment/integration), Linear delegate/@Oz, GitHub auth, verification, and when to route work to cloud PR agents vs linear-orchestrator."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [warp, oz, linear, cloud-agent, integration, devops, github, pr]
    related_skills: [warp-oz-cursor, warp-oz-router, warp-oz-deploy, warp-oz-monitor, warp-oz-github-actions, linear-webhook-bridge, deploy-pilot]
---

# Warp Oz × Linear

## Overview

Warp **Oz** 是雲端 coding agent 平台。Linear 裡 **Delegate → Oz** 或 `@Oz` 會在 Warp 雲端開 container、clone repo、跑 agent、開 PR。

這跟 **本地 Hermes**（`linear-orchestrator` + `hermes.exe`）是**兩條平行管線**，不是取代關係。

```
Linear issue
  ├─ Delegate → Hermes Agent  →  Windows :8645 → hermes.exe → comment/activity 回寫
  └─ Delegate → Oz            →  Warp cloud  → Docker env → PR + Linear 進度
```

官方文件：
- [Integrations Overview](https://docs.warp.dev/platform/integrations/)
- [Linear integration](https://docs.warp.dev/agent-platform/cloud-agents/integrations/linear/)
- [Integration setup (CLI)](https://docs.warp.dev/reference/cli/integration-setup/)
- [Oz Platform](https://docs.warp.dev/agent-platform/cloud-agents/platform/)

## When to Use

**用 Oz（雲端）當：**
- 需要 **clone repo、改 code、開 PR**
- 任務適合在隔離 Docker 環境跑（有 setup commands）
- 人類在 Linear 已 **Delegate → Oz** 或 comment `@Oz`
- 要 session sharing link 遠端看 agent 跑

**用 Hermes（本地）當：**
- 快問快答、查狀態、整理 issue、不開 PR
- 要用本地工具 / `~/.hermes` 記憶 / 現有 skills
- Linear **Delegate → Hermes Agent**
- 走 `https://webhooks.edgars.tools/webhooks/linear` → `linear-orchestrator`

**不要混用：** 同一張 issue 不要同時 delegate 兩個 agent。

## Prerequisites

| 項目 | 說明 |
|------|------|
| Warp 團隊 | Free 可建 team；integration 需 **Build/Max/Business** |
| Credits | ≥20（官方要求才能觸發 integration） |
| Email | Warp 登入 email = Linear workspace email |
| GitHub | 第一次觸發授權 Warp GitHub App |
| CLI | Windows：`C:\Program Files\Warp\warp.exe` + `$env:WARP_CLI_MODE='1'`；或 Warp 終端機內 `oz` |

### Edgar 現役 Environment（2026-07-01）

| Name | ID | Docker | Repo |
|------|-----|--------|------|
| `edgar-linear-dev` | `gMtdQHl184AFGV1DgM8eLk` | `python:3.11` | `Edgar-s-Tool/linear-orchestrator` |
| `deploy-pilot` | `24syFwqAf4M1SUPXZWEywM` | `warpdotdev/dev-base:latest` | `Edgars-tool/deploy-pilot` |
| `new world` | `C0onm8hL5yAcFPJO85EDp6` | `node22` | 多個 Edgars-tool repos |

**Linear integration：** 已連線（2026-07-01），綁定 `edgar-linear-dev`。

**本機一鍵腳本：**
- `V:\projects\linear-orchestrator\scripts\setup-warp-api.ps1` — 檢查登入、API、環境
- `V:\projects\linear-orchestrator\scripts\ask-warp.ps1` — 用白話叫 Warp 做事
- `V:\projects\linear-orchestrator\scripts\watch-warp-run.ps1` — 盯任務狀態與 follow-up
- `V:\projects\linear-orchestrator\scripts\install-warp-skills.ps1` — 安裝全部 Warp 技能到各 Agent

**相關技能：** `warp-oz-cursor`（Cursor 必叫 Warp）、`warp-oz-router`（分工表）、`warp-oz-deploy`、`warp-oz-monitor`、`warp-oz-github-actions`

## Procedure

### 1. 檢查 integration 狀態

在 **Warp 終端機**（一般 PowerShell 可能卡住）：

```powershell
$env:WARP_CLI_MODE = '1'
& 'C:\Program Files\Warp\warp.exe' integration list
& 'C:\Program Files\Warp\warp.exe' environment list
& 'C:\Program Files\Warp\warp.exe' credits
```

預期 Linear 列顯示 **connected**；若 `feature_not_available` → 升級方案或加 credits。

### 2. 首次設定（人類做一次）

**網頁（推薦）：** [oz.warp.dev](https://oz.warp.dev) → Environment → Linear integration → 瀏覽器安裝 Oz。

**CLI：**

```text
oz environment create \
  --name edgar-linear-dev \
  --docker-image python:3.11 \
  --repo Edgar-s-Tool/linear-orchestrator \
  --setup-command "pip install -e ."

oz integration create linear --environment gMtdQHl184AFGV1DgM8eLk
```

或跑 repo 腳本：`V:\projects\linear-orchestrator\scripts\setup-warp-linear.ps1`

### 3. Linear 觸發（人類瀏覽器）

1. Linear → Settings → Agents → 確認 **Oz** 已安裝
2. 開 issue → 右側 **Delegate → Oz**（或 comment `@Oz` 描述任務）
3. 預期：Oz ack → task list → 進度更新 → 可能 PR link

測試 issue：[EDG-289](https://linear.app/edgarstool/issue/EDG-289/test-oz-assign-smoke-test)

### 4. Hermes 內建議怎麼回應

當使用者問「這張單要給誰」：

| 需求關鍵字 | 建議 |
|-----------|------|
| 開 PR、改 repo、實作功能 | 建議 Linear **Delegate → Oz**，environment `edgar-linear-dev` |
| 解釋、摘要、本地查 log | 本地 Hermes / `linear-orchestrator` |
| 部署上線 | `deploy-pilot` skill + 視情況 Oz `deploy-pilot` env |

若使用者已在 Linear delegate Oz，**不要**再用本地 hermes 重複做同一件事。

### 5. 監控 Oz run

- Warp Agent Management Panel（Warp app）
- [oz.warp.dev](https://oz.warp.dev) runs 列表
- Linear issue 內 Oz 貼的 session link

## Verification

```powershell
# Integration 已連
$env:WARP_CLI_MODE='1'
& 'C:\Program Files\Warp\warp.exe' integration list
# Linear 列應為 connected

# Linear 有 Oz agent
# Settings → Agents → Oz 存在

# 觸發後
# issue 內有 Oz activity / PR link
```

## Common Pitfalls

1. **`oz` 在 Cursor PowerShell 無輸出** → 改在 **Warp 終端機**或 oz.warp.dev 操作
2. **`external_authentication_required`** → 重跑 GitHub / Linear 授權
3. **跟 Hermes 搶同一張 issue** → 只 delegate 一個 agent
4. **Public repo 沒授權 GitHub** → Oz 能讀不能寫 PR
5. **Environment repo 沒包含目標專案** → `oz environment update` 加 repo

## Related Paths

| 路徑 | 用途 |
|------|------|
| `V:\projects\linear-orchestrator\docs\WARP-OZ-LINEAR-SETUP.md` | 人類設定速查 |
| `V:\projects\linear-orchestrator\docs\WINDOWS-SETUP.md` | 本地 Hermes orchestrator |
| `V:\projects\linear-webhook-bridge\SKILL.md` | Linear → 本地 Hermes 四層管線 |
