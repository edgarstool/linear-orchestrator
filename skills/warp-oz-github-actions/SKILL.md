---
name: warp-oz-github-actions
description: "Use when setting up or maintaining GitHub Actions workflows that trigger Warp Oz for PR review, CI failure fixes, or automated code tasks. Covers oz-agent-action, agent API keys, and environment mapping."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [warp, oz, github-actions, ci, pr-review, automation]
    related_skills: [warp-oz-cursor, warp-oz-router, warp-oz-linear]
---

# Warp Oz × GitHub Actions

## Overview

GitHub Actions 可在 **PR 開啟**、**CI 失敗**、**issue 標籤** 等事件時自動叫 Warp Oz，在雲端改 code 或 review，結果回 PR comment / 新 PR。

```
GitHub event (PR / workflow_failure)
  └─ GitHub Actions job
       └─ oz-agent-action 或 curl POST /agent/run
            └─ Oz environment → clone → agent → PR / comment
```

官方文件：
- [GitHub Actions integration](https://docs.warp.dev/platform/integrations/github-actions/)
- [Oz API](https://docs.warp.dev/reference/api-and-sdk)
- [Team GitHub authorization](https://docs.warp.dev/platform/integrations/)（agent API key 用 GitHub App 開 PR）

## When to Use

| 情境 | 建議 workflow |
|------|---------------|
| PR opened / synchronize | Oz code review + 建議 |
| CI failed on `main` | Oz 開 fix PR |
| `needs-agent` label on issue | Oz 實作 + PR |
| Nightly dependency check | 搭配 `warp-oz-scheduled`（Oz schedule，非 GHA cron） |

**不要用 GHA 叫 Oz 當：**
- 每次 push 都跑（浪費 credits）— 用 path filter 或 PR only
- 純問答（用 Hermes）

## Prerequisites

| 項目 | 說明 |
|------|------|
| Warp 團隊 | Build+ 、credits ≥ 20 |
| Agent API key | oz.warp.dev → Settings → API Keys（team GitHub auth 建議開） |
| GitHub secret | repo `Settings → Secrets → WARP_API_KEY` |
| Environment | 與 repo 對應，見下方對照表 |

### Environment 對照（Edgar）

| Repo 類型 | Environment | `-Project` / env ID |
|-----------|-------------|---------------------|
| linear-orchestrator | `edgar-linear-dev` | `gMtdQHl184AFGV1DgM8eLk` |
| deploy-pilot | `deploy-pilot` | `24syFwqAf4M1SUPXZWEywM` |
| 其他 Edgars-tool | `new world` | `C0onm8hL5yAcFPJO85EDp6` |

## Setup (One-Time, Human)

### 1. Team GitHub authorization

Warp Admin Panel → Platform → 啟用 GitHub org，讓 **agent API key** 用 GitHub App 開 PR（非個人 token）。

### 2. Repo secret

```text
Name:  WARP_API_KEY
Value: wk-...（agent API key）
```

### 3. 加 workflow 檔

見下方範本，放入 `.github/workflows/oz-agent.yml`。

## Workflow Templates

### PR Review（PR 開啟時）

```yaml
name: Oz PR Review

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  oz-review:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Oz review
        uses: warpdotdev/oz-agent-action@v1
        with:
          api-key: ${{ secrets.WARP_API_KEY }}
          prompt: |
            Review PR #${{ github.event.pull_request.number }} in ${{ github.repository }}.
            Branch: ${{ github.head_ref }} → ${{ github.base_ref }}.
            List bugs, security issues, and missing tests. Suggest concrete fixes.
            Do not merge; comment findings in the PR if possible.
          environment-id: gMtdQHl184AFGV1DgM8eLk
```

> 若 `oz-agent-action` 版本或參數與官方文件不同，以 [GitHub Actions 文件](https://docs.warp.dev/platform/integrations/github-actions/) 為準。

### CI 失敗自動修（workflow_run）

```yaml
name: Oz CI Fix

on:
  workflow_run:
    workflows: [CI]
    types: [completed]

jobs:
  oz-fix:
    if: ${{ github.event.workflow_run.conclusion == 'failure' && github.event.workflow_run.head_branch == 'main' }}
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Oz fix
        env:
          WARP_API_KEY: ${{ secrets.WARP_API_KEY }}
        run: |
          curl -sS -X POST https://app.warp.dev/api/v1/agent/run \
            -H "Authorization: Bearer $WARP_API_KEY" \
            -H "Content-Type: application/json" \
            -d '{
              "prompt": "CI failed on main for '"${{ github.repository }}"'. Inspect recent failures, fix root cause, open a PR with [Oz-CI] prefix.",
              "title": "Oz CI fix: ${{ github.repository }}",
              "config": {
                "environment_id": "C0onm8hL5yAcFPJO85EDp6",
                "name": "new world"
              }
            }'
```

### 用 curl 的通用範本

與 [`ask-warp.ps1`](V:\projects\linear-orchestrator\scripts\ask-warp.ps1) 相同 body 結構，適合 Linux runner。

## Agent Procedure

1. 確認 repo 應綁哪個 `environment_id`
2. 確認 `WARP_API_KEY` secret 已設（提醒 Edgar，不要 commit key）
3. 新增或更新 `.github/workflows/oz-*.yml`
4. PR 合併後在 Actions 頁看首次觸發
5. 失敗時查 Oz run：`oz.warp.dev` 或 `watch-warp-run.ps1`（本地用 Run ID）

## Recommended Repos (Edgar)

優先掛載：
- `Edgar-s-Tool/linear-orchestrator` → `edgar-linear-dev`
- `Edgars-tool/hermes-inn-UI` → `new world`
- `Edgars-tool/deploy-pilot` → `deploy-pilot`

## Verification

1. 開測試 PR → Actions 應觸發 Oz job
2. [oz.warp.dev](https://oz.warp.dev) 出現對應 run
3. PR 或 issue 有 Oz 回覆或新 PR

## Common Pitfalls

1. **用個人 API key 但沒 write 權** → 開 team GitHub authorization
2. **environment 沒包含該 repo** → oz.warp.dev 加 repo
3. **每次 push 都觸發** → 限 `pull_request` 或 path filters
4. **secret 名稱打錯** → 必須 `WARP_API_KEY`
5. **與 Linear Oz 搶同一任務** → 同一 issue 只一條自動化管線

## Related Paths

| 路徑 | 用途 |
|------|------|
| `V:\projects\linear-orchestrator\scripts\ask-warp.ps1` | 本地同等 API 呼叫 |
| `V:\projects\linear-orchestrator\skills\warp-oz-router\SKILL.md` | 何時用 GHA vs Cursor 叫 Oz |
| `V:\projects\linear-orchestrator\docs\WARP-OZ-LINEAR-SETUP.md` | Warp 整體設定 |

## Note on Slack

若團隊改用 Slack `@Oz`，見 `warp-oz-slack`（可另建）；本技能專注 **GitHub Actions**。計畫二選一時預設實作 GHA，因無需額外 Slack workspace 授權。
