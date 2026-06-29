# Tunnel migration: webhooks.edgars.tools → Windows localhost:8645

最後更新：2026-06-30

## 現況（Windows 原生）

- **linear-orchestrator** 跑在 **Windows** `0.0.0.0:8645`（不是 WSL）
- `http://127.0.0.1:8645/healthz` 本機應回 200
- **Cloudflared** 以 Windows 服務跑 `edgar-local-01-tunnel`（token-based，Dashboard 管路由）
- 正式公開 hostname：**webhooks.edgars.tools**（複數 webhooks，domain edgars.tools）

Linear webhook 進不來通常是：

1. Dashboard tunnel 裡 **webhooks.edgars.tools** 還沒加、或指 **localhost:8644**（舊 hermes gateway）或 **WSL IP:8645**
2. orchestrator 沒在 Windows 跑
3. Linear App 仍指舊 URL **webhook.whoasked.vip**（已拔除）

## 一步修好：加 / 改 dashboard route

1. 開 <https://one.dash.cloudflare.com/> → **Networks → Tunnels → edgar-local-01-tunnel → Public Hostname**
2. **Add a public hostname**（或編輯既有）：
   - Subdomain: `webhooks`
   - Domain: `edgars.tools`
   - Service: **`http://localhost:8645`**
3. 存檔 → 等幾秒 → `https://webhooks.edgars.tools/healthz` 應 200
4. Linear App → Webhook URL → `https://webhooks.edgars.tools/webhooks/linear`

> **不要**再用 `http://172.30.x.x:8645` 或 **webhook.whoasked.vip**。WSL / whoasked 已退出這條路。

DNS 會自動 CNAME 到 tunnel（同 **mcp.edgars.tools**）。勿手動 A 到 `127.0.0.1`。

## 啟動 orchestrator（Windows）

```powershell
cd G:\AI_WORK_512\repos\linear-orchestrator
powershell -ExecutionPolicy Bypass -File .\scripts\Start-LinearOrchestrator.ps1 -Wait
powershell -ExecutionPolicy Bypass -File .\scripts\Check-LinearOrchestrator.ps1 -Public
```

## 驗證

```powershell
# 本機
Invoke-WebRequest http://127.0.0.1:8645/healthz -UseBasicParsing

# 公網
Invoke-WebRequest https://webhooks.edgars.tools/healthz -UseBasicParsing
```

簽章測試 webhook 見 `G:\AI_WORK_512\repos\cloudflared\HERMES-WEBHOOK.md`。

## 為什麼不能本地改 token tunnel

Cloudflare token tunnel 的 ingress 只在 Dashboard 改。本地 YAML（舊 home-tunnel）已 DEPRECATED。
