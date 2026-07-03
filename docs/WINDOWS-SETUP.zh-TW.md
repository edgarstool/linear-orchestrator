# linear-orchestrator — Windows 原生版（給德德）

> 最後更新：2026-06-30  
> **不用 WSL**。Hermes 用桌面版 APP，orchestrator 用 Windows Python 跑。

---

## 這是什麼？

你在 Linear 委派 issue 給 Hermes 時，需要一個 **always-on 小服務** 接 webhook、10 秒內回「收到了」、叫 Hermes 做事、再把結果寫回 Linear。

這個服務叫 **linear-orchestrator**，現在改在 **Windows** 跑，port **8645**。

---

## 第一次安裝（做一次就好）

在 **PowerShell**：

```powershell
cd G:\AI_WORK_512\repos\linear-orchestrator
powershell -ExecutionPolicy Bypass -File .\scripts\Install-LinearOrchestratorWindows.ps1
```

這會建立 `.venv` 並安裝 Python 套件。

### 環境變數（密碼）

orchestrator 需要這些（名稱一字不差）：

| 變數 | 用途 |
|------|------|
| `LINEAR_API_KEY` | 讀寫 Linear issue |
| `LINEAR_WEBHOOK_SECRET` | 驗證 webhook 簽章（workspace webhook） |
| `LINEAR_OAUTH_WEBHOOK_SECRET` | **Hermes Agent OAuth App** 的 Signing secret（委派 AgentSessionEvent 用；跟 workspace 不同） |
| `LINEAR_OAUTH_CLIENT_ID` | 委派回寫 Linear（OAuth App） |
| `LINEAR_OAUTH_CLIENT_SECRET` | 同上 |
| `HERMES_PATH` | Hermes CLI 路徑（可選，會自動找） |

**放哪裡（二選一）：**

1. **`C:\Users\<你>\.hermes\.env`** — 跟 Hermes 桌面版同一資料夾（推薦）
2. **Doppler** `handcraft-mcp` / `prd` — 腳本會自動 `doppler run`，並把 `LINEAR_CLIENT_ID` 對應成 `LINEAR_OAUTH_CLIENT_ID`

> 若你之前只在 WSL 有 `.env`，可一次性複製（不會顯示內容）：
> ```powershell
> wsl -d Ubuntu-24.04-G -e cat /home/edgar/.hermes/.env | Out-File "$env:USERPROFILE\.hermes\.env" -Encoding utf8NoBOM
> ```

**不要**把 secret 貼在聊天或 commit 進 git。

---

## 日常操作

```powershell
cd G:\AI_WORK_512\repos\linear-orchestrator

# 啟動（背景）
powershell -ExecutionPolicy Bypass -File .\scripts\Start-LinearOrchestrator.ps1 -Wait

# 檢查
powershell -ExecutionPolicy Bypass -File .\scripts\Check-LinearOrchestrator.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\Check-LinearOrchestrator.ps1 -Public

# 停止
powershell -ExecutionPolicy Bypass -File .\scripts\Stop-LinearOrchestrator.ps1
```

本機健康檢查：瀏覽器開 <http://127.0.0.1:8645/healthz> 或 dashboard <http://127.0.0.1:8645/>

Log / PID 在：`G:\AI_WORK_512\run\linear-orchestrator\`

---

## 開機自動啟動

```cmd
G:\AI_WORK_512\repos\linear-orchestrator\scripts\install-windows-scheduled-task.cmd
```

這會建立 Windows「登入時執行」排程，不用 WSL。

---

## Cloudflare Tunnel（公開 webhook）

你的 **Cloudflared Windows 服務** 已跑 `edgar-local-01-tunnel`。

在 [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)：

**Networks → Tunnels → edgar-local-01-tunnel → Public Hostname**

把 **webhooks.edgars.tools** 的 Service 設成：

```
http://localhost:8645
```

> **不要**再填 WSL IP（172.30.x.x）。Windows 本機 localhost 就夠了。

存檔後幾秒，<https://webhooks.edgars.tools/healthz> 應回 200。

若還是 530/502：確認 orchestrator 有在跑 + tunnel hostname 指到 **8645** 不是舊的 **8644**。

### ⚠️ WSL 搶 port（常見根因）

若 WSL 裡還有舊的 `python -m linear_orchestrator` 在跑：

- `wslrelay` 會佔 `127.0.0.1:8645`
- Cloudflare tunnel 指 `http://localhost:8645` 時，**流量進 WSL 舊版**，不是 Windows 新版
- `healthz` 仍可能 200，但 **委派 webhook 會進錯機器或驗簽失敗** → Linear 顯示 Did not respond

檢查：

```powershell
netstat -ano | findstr ":8645"
powershell -ExecutionPolicy Bypass -File .\scripts\Check-LinearOrchestrator.ps1
```

啟動腳本會自動 `pkill` WSL 舊版；也可手動：

```powershell
wsl -e bash -lc "pkill -f 'python -m linear_orchestrator' || true"
powershell -ExecutionPolicy Bypass -File .\scripts\Start-LinearOrchestrator.ps1 -Wait
```

---

## Hermes 桌面版

- 設定目錄：`C:\Users\<你>\.hermes\`
- Hermes CLI 通常在：`C:\Users\<你>\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe`
- orchestrator 會用 CLI 叫 Hermes 做事（`--skills linear`），**不需要**再跑 WSL gateway 8644

---

## 相關文件

| 文件 | 用途 |
|------|------|
| `./WINDOWS-SETUP.zh-TW.md` | 本文件 |
| `G:\AI_WORK_512\repos\cloudflared\HERMES-WEBHOOK.md` | Tunnel + 架構 |
| `V:\projects\mcp-handcraft\docs\Linear-Agent人類委派-新手版.md` | Linear 委派流程 |
