# linear-orchestrator

Linear webhook → Hermes 中介層。修掉「Did not respond」的根因：webhook 不該直接餵 hermes。

## 4 層架構

```
Linear  →  Cloudflare edge  →  cloudflared tunnel  →  127.0.0.1:8645
                                                            │
                                                            ▼
        ┌────────────────────────────────────────────────────────────┐
        │  linear-orchestrator (aiohttp service, this repo)          │
        │                                                            │
        │   1) sig       ── verify Linear-Signature + ±60s timestamp │
        │   2) parser    ── normalise payload → {issue, action, ...} │
        │   3) session   ── map Linear issue/agent_session → hermes  │
        │                   session id (連續對話、不重複問)          │
        │   4) runner    ── 呼 hermes (CLI or API server 8642)       │
        │   5) writer    ── 透過 Linear GraphQL 把回覆寫回 issue     │
        └────────────────────────────────────────────────────────────┘
                                                            │
                                                            ▼
                                                    Linear issue comment
```

## 為什麼需要這層

- Hermes 內建 webhook gateway 只會「收下 + 跑 agent + log」，**不會把結果寫回 Linear**，所以 issue 永遠顯示 "Did not respond"。
- Webhook payload 是 JSON，直接當 prompt 等於亂塞，agent 沒有結構化上下文。
- 同一 issue 連續事件要保持對話延續，需要 session 映射。
- Linear Agent Session 協定需要回應 `agentSessionActivityCreate`，不是普通 comment。

## 安裝（Windows 原生 — 推薦）

Repo 主場：`G:\AI_WORK_512\repos\linear-orchestrator`

```powershell
cd G:\AI_WORK_512\repos\linear-orchestrator
powershell -ExecutionPolicy Bypass -File .\scripts\Install-LinearOrchestratorWindows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\Start-LinearOrchestrator.ps1 -Wait
powershell -ExecutionPolicy Bypass -File .\scripts\Check-LinearOrchestrator.ps1
```

環境變數放 `C:\Users\<你>\.hermes\.env` 或透過 Doppler `handcraft-mcp/prd`。詳見 `docs/WINDOWS-SETUP.zh-TW.md`。

開機自啟：`scripts\install-windows-scheduled-task.cmd`

## 安裝（WSL Ubuntu — 舊路徑，可選）

```bash
git clone https://github.com/Edgar-s-Tool/linear-orchestrator.git ~/linear-orchestrator
cd ~/linear-orchestrator
bash scripts/install.sh
bash scripts/install-systemd.sh   # 選用
```

## 操作（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-LinearOrchestrator.ps1
powershell -ExecutionPolicy Bypass -File scripts\Check-LinearOrchestrator.ps1
powershell -ExecutionPolicy Bypass -File scripts\Stop-LinearOrchestrator.ps1
```

Dashboard：`http://127.0.0.1:8645/`

## tunnel 整合

Token tunnel **edgar-local-01-tunnel**（Cloudflare Dashboard 管理）：

```
webhooks.edgars.tools → http://localhost:8645
```

（舊 `webhook.whoasked.vip` 路由已移除；勿再用 WSL IP。）

Cloudflared 跑在 Windows 服務即可。
## Session 規則

| Event 類型 | session key | 行為 |
|---|---|---|
| `AgentSessionEvent` | `linear-as-<agent_session_id>` | 10 秒內回 `thought`，完成後回 `response`（`agentActivityCreate`） |
| `Issue` 被指派給 agent | `linear-issue-<identifier>` | 回 ack comment |
| `Comment` 提到 agent | `linear-issue-<identifier>` | 接續對話，回 comment |
| 其他 | — | log + skip |

## 清理與資源回收

任務結束後採 best-effort、non-blocking 清理，避免殘留膨脹記憶體或留下過時狀態：

- **背景任務**：每個 webhook 觸發的 `_process` 任務都登記在 `app["_pending"]`，完成 / 失敗 / 取消時透過 done callback 自動移除，`_pending` 只保留真正在跑的工作。
- **hermes worker session**：hermes 以 `start_new_session=True` 啟動、自成 process group。逾時或本服務關閉時，會對整個 process group 送 `SIGKILL`（POSIX）並 reap，避免 hermes 衍生的孫程序變孤兒殘留；已結束的程序則跳過。清理邏輯冪等且不會拋錯。
- **payload 檔**：`payloads/` 內超過 7 天的 dump 由背景 loop 自動刪除。

## 依賴

- Python 3.10+（Windows 或 WSL）
- `aiohttp`, `pyyaml`, `python-dotenv`
- hermes CLI 已裝
- Linear personal API key（可讀寫 issue / comment）

## License

MIT
