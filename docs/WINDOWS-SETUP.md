# linear-orchestrator — Windows 原生設定（不用 WSL）

最後更新：2026-07-01

## 架構

```
Linear 瀏覽器 assign/delegate
    → https://webhooks.edgars.tools/webhooks/linear  (或 webhook.whoasked.vip)
    → Cloudflare tunnel edgar-local-01-tunnel → http://localhost:8645
    → linear-orchestrator (Windows Python)
    → hermes.exe
    → Linear agentActivityCreate / comment 回寫
```

參考：
- [Linear Webhooks](https://linear.app/developers/webhooks) — `Linear-Signature` HMAC-SHA256、5 秒內 200
- [Hermes webhook 章節](https://github.com/NousResearch/hermes-agent) — `~/.hermes/config.yaml` routes（本 repo 用獨立 orchestrator 取代 gateway 直餵）

## 1. 安裝

```powershell
cd V:\projects\linear-orchestrator
py -3.13 -m venv .venv
.\.venv\Scripts\pip install -e .
```

## 2. 環境變數（`%USERPROFILE%\.hermes\.env`）

| 變數 | 必填 | 用途 |
|------|------|------|
| `LINEAR_API_KEY` | 是 | comment 回寫 |
| `LINEAR_WEBHOOK_SECRET` | 是 | webhook HMAC 驗章 |
| `LINEAR_OAUTH_CLIENT_ID` / `LINEAR_OAUTH_CLIENT_SECRET` | 是 | assign → `agentActivityCreate`（10 秒 thought） |
| `AGENT_LINEAR_USER_ID` | 是 | 辨識 delegate 給 Hermes |
| `HERMES_PATH` | 建議 | 例：`%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe` |

**重要**：Hermes OAuth App 的 webhook URL 也須指向  
`https://webhooks.edgars.tools/webhooks/linear`  
（Linear → Settings → API → 你的 OAuth App）。  
否則 workspace webhook 收得到 comment，但 **AgentSessionEvent（assign）** 可能進不來。

## 3. 啟動

```powershell
powershell -File V:\projects\linear-orchestrator\scripts\start-windows.ps1
curl http://127.0.0.1:8645/healthz
```

## 4. 驗證

```powershell
# 簽章測試（本機 + 公網）
powershell -File scripts\test-windows.ps1
powershell -File scripts\test-windows.ps1 -Url https://webhooks.edgars.tools/webhooks/linear

# Assign / AgentSession 模擬（用真實 pending session）
powershell -File scripts\test-assign-windows.ps1 -UseLatestPendingSession -IssueIdentifier EDG-286
```

Dashboard：`http://127.0.0.1:8645/`

## 5. 瀏覽器真人測試（assign 一次）

1. 開 Linear issue（例：[EDG-286](https://linear.app/edgarstool/issue/EDG-286/test-hermes-assign-smoke-test)）
2. 右側 **Delegate** → 選 **Hermes Agent**
3. <10 秒內應看到 thought「收到委派…」
4. 1–3 分鐘內看到最終 response

## 6. Cloudflare tunnel

公網 hostname（token tunnel `edgar-local-01-tunnel`）：

| Hostname | Service |
|----------|---------|
| `webhooks.edgars.tools` | `http://localhost:8645` |
| `webhook.whoasked.vip` | `http://localhost:8645` |

Linear 已註冊 webhook：`https://webhooks.edgars.tools/webhooks/linear`
