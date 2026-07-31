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

## Runtime 狀態與恢復

關鍵可變狀態（session 對應、delivery 紀錄、webhook payload）都存在單一 SQLite state root，
預設 `~/.local/share/linear-orchestrator`，可用 `LINEAR_ORCHESTRATOR_STATE_DIR` 指到持久化儲存。
服務啟動時會自動恢復被當機／部署中斷的 delivery。

```bash
curl -s http://127.0.0.1:8645/state | jq          # 狀態位置、筆數、integrity、上次恢復結果
python3 -m linear_orchestrator.state_cli inspect  # 不需服務在跑
python3 -m linear_orchestrator.state_cli backup --keep 7
python3 -m linear_orchestrator.state_cli restore <snapshot>.db --force
```

備份範圍、恢復步驟、哪些檔案可以安全刪除：`docs/STATE-PERSISTENCE.zh-TW.md`

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

## 依賴

- Python 3.10+（Windows 或 WSL）
- `aiohttp`, `pyyaml`, `python-dotenv`
- hermes CLI 已裝
- Linear personal API key（可讀寫 issue / comment）

## License

MIT
