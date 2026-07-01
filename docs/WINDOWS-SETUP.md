# linear-orchestrator — Windows 設定（不用 WSL）

## 架構

```
Linear 瀏覽器 assign/delegate
    → https://webhooks.edgars.tools/webhooks/linear  (Cloudflare tunnel)
    → Windows localhost:8645  (linear-orchestrator)
    → hermes.exe
    → Linear agentActivityCreate / comment 回寫
```

官方參考：
- [Linear Webhooks](https://linear.app/developers/webhooks) — `Linear-Signature` HMAC-SHA256
- [Linear Agents](https://linear.app/developers/agents) — delegate + AgentSessionEvent
- [Agent Interaction](https://linear.app/developers/agent-interaction) — 10 秒內 `thought` ack

## 1. 環境變數（`%USERPROFILE%\.hermes\.env`）

| 變數 | 必填 | 用途 |
|------|------|------|
| `LINEAR_WEBHOOK_SECRET` | 是 | Workspace webhook 驗章 |
| `LINEAR_OAUTH_WEBHOOK_SECRET` | 建議 | Hermes OAuth app 的 AgentSession webhook 驗章（Linear Developer → Application → Webhooks） |
| `LINEAR_API_KEY` | 是 | comment 回寫 |
| `LINEAR_OAUTH_CLIENT_ID` / `SECRET` | 是 | `agentActivityCreate`（assign 流程） |
| `AGENT_LINEAR_USER_ID` | 是 | Hermes Agent 的 Linear user id |
| `HERMES_PATH` | 是 | 例如 `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe` |

## 2. 啟動 orchestrator

```powershell
cd V:\projects\linear-orchestrator
python -m venv .venv
.\.venv\Scripts\pip install -e .
.\scripts\start-windows.ps1
```

Dashboard：`http://127.0.0.1:8645/`

## 3. 驗證 webhook

```powershell
# 公網 healthz（應 200）
curl -i https://webhooks.edgars.tools/healthz

# 本機 signed 測試
.\scripts\test-assign-windows.ps1 -IssueIdentifier EDG-287
```

## 4. 瀏覽器 assign 測試

1. Linear 開 issue，右側 **Delegate** → **Hermes Agent**
2. 10 秒內應看到 thought「收到委派…」
3. 完成後有 response

> 注意：Linear 新版用 **Delegate**（不是 Assignee）把工單交給 agent。

若仍「Did not respond」：多半是 **OAuth Application webhook** 沒設好（不是 workspace webhook）。
請開 https://linear.app/settings/api/applications → Hermes → Webhooks：
URL = `https://webhooks.edgars.tools/webhooks/linear`，勾 **Agent session events**，Signing secret 貼到 `LINEAR_OAUTH_WEBHOOK_SECRET`。

**備援（webhook 漏送時）**：另開 PowerShell 常駐 `.\scripts\poll-agent-sessions.ps1`，每 3 秒輪詢 pending session 並本機觸發 Hermes。

診斷：`http://127.0.0.1:8645/diag`（secrets 數量）、`/rejects`（Linear 有打到但驗章失敗）。

## 5. Warp Oz（雲端 agent）

```powershell
.\scripts\setup-warp-linear.ps1
```

或開 [oz.warp.dev](https://oz.warp.dev) 用精靈連接 Linear。完成後在 Linear **Delegate → Oz** 測試。

## Tunnel 備註

- **現役 URL**：`https://webhooks.edgars.tools/webhooks/linear`（已指向 Windows `:8645`）
- `webhook.whoasked.vip` 若仍 530，可忽略（Linear webhook 已改用 edgars.tools）
