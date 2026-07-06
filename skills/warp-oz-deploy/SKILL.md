---
name: warp-oz-deploy
description: "Use when deploying via deploy-pilot through Warp Oz deploy-pilot environment. Covers ask-warp -Project deploy, detect→deploy→healthcheck→rollback acceptance prompts, and session_link handoff."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [warp, oz, deploy, deploy-pilot, devops, healthcheck, rollback]
    related_skills: [warp-oz-cursor, warp-oz-router, deploy-pilot]
---

# Warp Oz × Deploy-Pilot

## Overview

部署上線走 **deploy-pilot** 技能 + **Oz `deploy-pilot` environment**，不在 Cursor 本地直接 deploy production。

| 項目 | 值 |
|------|-----|
| Environment 名稱 | `deploy-pilot` |
| Environment ID | `24syFwqAf4M1SUPXZWEywM` |
| Docker | `warpdotdev/dev-base:latest` |
| 主 repo | `Edgars-tool/deploy-pilot` |
| 觸發 | `ask-warp.ps1 -Project deploy` |

本地 [`deploy-pilot` skill](V:\projects\deploy-pilot\SKILL.md) 定義流程：`detect → compose → healthcheck → rollback`。

Oz 在雲端執行相同邏輯，適合需要隔離環境、可審計的部署任務。

## When to Use

- staging / production 部署請求
- 需要 healthcheck + 失敗自動 rollback
- Edgar 或 Linear issue 明確說「部署」「上線」
- 不確定用 docker / pm2 / systemd → 讓 Oz 跑 `detect` 再決定

**不要用 Oz deploy 當：**
- 純本地開發 `npm run dev`
- 只問「怎麼部署」不實際執行（用 Hermes 解釋即可）

## Procedure

### 1. 確認部署目標

向 Edgar 或 Linear issue 確認：
- 要部署哪個 **repo**、哪個 **分支**
- 目標環境（staging / production）
- health endpoint URL（若有）

### 2. 組 Prompt（必含驗收標準）

使用下方範本，替換 `{...}` 欄位。

### 3. 叫 Warp

```powershell
cd V:\projects\linear-orchestrator
.\scripts\ask-warp.ps1 -Project deploy -Prompt "<完整 prompt>"
```

需要等完成時加 `-Wait`，或之後用 `watch-warp-run.ps1`。

### 4. 回報

貼 **session_link** 給 Edgar；完成後摘要：成功 / 失敗 / 是否 rollback。

## Prompt Templates

### 標準 Compose 部署

```text
Repo: Edgars-tool/{app-repo}，分支 {branch}。
使用 deploy-pilot 流程部署到 {staging|production}。

步驟：
1. detect 環境（Compose 優先）
2. deploy
3. healthcheck：{health_url} 必須回 200
4. 失敗則 rollback 並在結果說明原因

驗收：
- 部署成功且 healthcheck 通過
- 或已 rollback 且附失敗原因
- 若有設定變更，列出改了什麼（不要含 secrets）
```

### 僅偵測環境（不部署）

```text
Repo: Edgars-tool/{app-repo}。
只跑 deploy-pilot detect，回報建議的部署模式（docker compose / pm2 / systemd）與理由。不要實際部署。
```

### Staging 冒煙測試後部署

```text
Repo: Edgars-tool/{app-repo}，分支 {branch}。
先確認 CI 綠燈，再 deploy 到 staging。
Health: GET {url}/health → 200。
完成後貼部署摘要與 session link。
```

## Integration with deploy-pilot Skill

Oz environment 已 clone `deploy-pilot` repo。Prompt 可引用：

```bash
./deploy-pilot.sh detect
./deploy-pilot.sh deploy
./deploy-pilot.sh status
./deploy-pilot.sh rollback
```

Compose-first：未指定模式時走 Docker Compose。

## Verification

```powershell
cd V:\projects\linear-orchestrator
.\scripts\ask-warp.ps1 -Project deploy -Prompt "讀 deploy-pilot README，用三句話說明 detect 流程，不要實際部署"
```

預期：Run ID + session_link；Oz 回覆摘要。

## Common Pitfalls

1. **用 `-Project general` 部署** → 應用 `deploy`
2. **Prompt 沒寫 health URL** → Oz 無法驗收
3. **production 部署沒確認** → 高風險改動先問 Edgar
4. **secrets 寫進 prompt** → 禁止；用 environment secrets / Warp agent secrets
5. **本地 Cursor 直接 deploy prod** → 應走本技能 + Oz

## Related Paths

| 路徑 | 用途 |
|------|------|
| `V:\projects\deploy-pilot\SKILL.md` | 部署流程定義 |
| `V:\projects\linear-orchestrator\scripts\ask-warp.ps1` | `-Project deploy` |
| `V:\projects\linear-orchestrator\skills\warp-oz-monitor\SKILL.md` | 盯部署任務完成 |
