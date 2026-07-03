# EDG-70 最終 Cutover 操作手冊

> Issue: https://linear.app/edgarstool/issue/EDG-70/s10-04-執行最終-cutover-並確認新-workspace-為唯一主工作區  
> 最後更新：2026-07-03

## 目標

執行最終 cutover，確認 **Windows 原生 linear-orchestrator** 為唯一主工作區，並停用所有舊路由。

| 項目 | 舊（已棄用） | 新（唯一主工作區） |
|------|-------------|------------------|
| Webhook URL | `https://webhook.whoasked.vip/webhooks/linear` | `https://webhooks.edgars.tools/webhooks/linear` |
| 執行環境 | WSL Ubuntu，`python -m linear_orchestrator` | Windows 原生，port **8645** |
| Cloudflare Tunnel | `home-tunnel`（YAML 管路由，deprecated） | `edgar-local-01-tunnel`（Dashboard 管路由） |

---

## 前置條件

- [ ] Hermes 桌面版已安裝於 Windows（`C:\Users\EdgarsTool\AppData\Local\hermes\`）
- [ ] `.venv` 已建立（執行過 `Install-LinearOrchestratorWindows.ps1`）
- [ ] `C:\Users\EdgarsTool\.hermes\.env`（或 Doppler `handcraft-mcp/prd`）包含以下必要變數：
  - `LINEAR_API_KEY`
  - `LINEAR_WEBHOOK_SECRET`（workspace webhook 簽章，**必備**）
  - `LINEAR_OAUTH_WEBHOOK_SECRET`（Hermes Agent OAuth App 簽章，**委派必備**）
- [ ] Cloudflared Windows 服務已跑（`edgar-local-01-tunnel`）

---

## Cutover 步驟

### 步驟 1：確認沒有 WSL 舊服務佔 port 8645

```powershell
netstat -ano | findstr ":8645"
```

若有結果且 LocalAddress 是 `127.0.0.1:8645`（wslrelay），則停掉 WSL 舊服務：

```powershell
wsl -e bash -lc "pkill -f 'python -m linear_orchestrator' || true"
Start-Sleep -Seconds 2
```

### 步驟 2：啟動 Windows orchestrator

```powershell
cd G:\AI_WORK_512\repos\linear-orchestrator
powershell -ExecutionPolicy Bypass -File .\scripts\Start-LinearOrchestrator.ps1 -Wait
```

`-Wait` 旗標會等到本機 healthz 回 200 才繼續。

### 步驟 3：更新 Cloudflare Tunnel 路由（新）

1. 開 <https://one.dash.cloudflare.com/> → **Networks → Tunnels → edgar-local-01-tunnel → Public Hostname**
2. 確認（或新增）：
   - Subdomain: `webhooks`
   - Domain: `edgars.tools`
   - Service: `http://localhost:8645`
3. 儲存 → 等 10–30 秒

### 步驟 4：移除舊 Cloudflare Tunnel 路由（舊）

1. 同一 Dashboard，找 `webhook.whoasked.vip` 的 Public Hostname
2. 刪除該路由（或將 Service 改成一個不存在的 port，讓它無效）

> **注意**：舊 `home-tunnel`（YAML 管路由）已 deprecated，不要再改它的 config。

### 步驟 5：更新 Linear Webhook 設定

1. 開 Linear App → **Settings → API → Webhooks**
2. 找到 **workspace webhook**（agent 也用這個）
3. 確認 URL 為 `https://webhooks.edgars.tools/webhooks/linear`
4. 若還是舊 URL，改掉並儲存

### 步驟 6：開機自動啟動（選用）

若尚未設定登入時自啟：

```cmd
G:\AI_WORK_512\repos\linear-orchestrator\scripts\install-windows-scheduled-task.cmd
```

---

## 驗證

執行確認腳本，所有項目必須通過：

```powershell
cd G:\AI_WORK_512\repos\linear-orchestrator
powershell -ExecutionPolicy Bypass -File .\scripts\Confirm-Cutover.ps1
```

腳本會檢查以下 5 項：

| 項目 | 說明 |
|------|------|
| Windows orchestrator 程序在跑 | PID file 存在且程序有效 |
| 本機 healthz 200 | `http://127.0.0.1:8645/healthz` |
| 無 WSL port-8645 衝突 | wslrelay 未搶佔 :8645 |
| 公開 healthz 200 | `https://webhooks.edgars.tools/healthz` |
| 舊 URL 已停用 | `webhook.whoasked.vip` 無法連線 |

全部通過後 exit code 0，cutover 完成。

### 手動快速驗證

```powershell
# 本機
Invoke-WebRequest http://127.0.0.1:8645/healthz -UseBasicParsing

# 公網
Invoke-WebRequest https://webhooks.edgars.tools/healthz -UseBasicParsing

# Check script（含 WSL 衝突檢查 + 公開健康）
powershell -ExecutionPolicy Bypass -File .\scripts\Check-LinearOrchestrator.ps1 -Public
```

---

## 常見問題

### 公開 healthz 回 530 / 502

原因：Cloudflare Tunnel 路由未正確指到 `localhost:8645`。  
修復：重新確認步驟 3，確認 Service 是 `http://localhost:8645`（不是 8644）。

### healthz 200 但委派仍顯示「Did not respond」

原因：WSL 舊服務還在 port 8645，wslrelay 把流量導到舊版（驗簽失敗）。  
修復：執行步驟 1 停掉 WSL 舊服務，再執行步驟 2 重啟 Windows 版。

### `LINEAR_WEBHOOK_SECRET` missing

原因：`.env` 缺少 workspace webhook 簽章 secret。  
修復：查 Linear App → Settings → API → Webhooks → 你的 webhook → Signing secret，加到 `.env`：

```
LINEAR_WEBHOOK_SECRET=lin_wh_xxxx
```

---

## Cutover 完成標誌

- `scripts/Confirm-Cutover.ps1` 全 PASS（exit 0）
- Linear 委派 issue 給 Hermes → 10 秒內收到 thought ack → Hermes 回覆出現在 issue comment
- `webhook.whoasked.vip` 任何路由已從 Cloudflare Dashboard 刪除
