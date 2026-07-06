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

## 安裝（WSL Ubuntu）

```bash
git clone https://github.com/Edgar-s-Tool/linear-orchestrator.git ~/linear-orchestrator
cd ~/linear-orchestrator
bash scripts/install.sh           # 建 venv + 裝相依
bash scripts/install-systemd.sh   # 選用：設為 systemd service，開機自啟（需 sudo）
```

開機自啟前需確認 WSL systemd 已啟用：

```bash
# 在 WSL 內
grep -q '^systemd=true' /etc/wsl.conf || { echo -e '[boot]\nsystemd=true' | sudo tee -a /etc/wsl.conf; }
# 然後在 Windows PowerShell：wsl --shutdown
```

裝完開 `http://127.0.0.1:8645/` 看內建 dashboard（最近 sessions / deliveries + NDJSON live stream）。

要在 `~/.hermes/.env`（會被 service 讀取）已經有：

```
LINEAR_API_KEY=lin_api_...
LINEAR_WEBHOOK_SECRET=lin_wh_...
HERMES_PATH=/home/edgar/.local/bin/hermes
```

## 操作

```bash
sudo systemctl start  linear-orchestrator
sudo systemctl status linear-orchestrator
journalctl -u linear-orchestrator -f
```

或非 systemd：

```bash
bash scripts/start.sh   # nohup 背景跑
bash scripts/stop.sh
bash scripts/test.sh    # 自製簽章測試端到端
```

## tunnel 整合

`~/.cloudflared/config.yml` ingress 把 `webhook.whoasked.vip` 從原本指向 hermes 8644 改成指這個 service：

```yaml
- hostname: webhook.whoasked.vip
  service: http://<WSL_IP>:8645
```

scripts/update-ingress.cmd 會幫忙自動偵測 WSL IP + 改 + 重啟 tunnel。

## Session 規則

| Event 類型 | session key | 行為 |
|---|---|---|
| `AgentSessionEvent` | `linear-as-<agent_session_id>` | 走 Linear Agent Session 協定，回 `agentSessionActivityCreate` |
| `Issue` 被指派給 agent | `linear-issue-<identifier>` | 回 ack comment |
| `Comment` 提到 agent | `linear-issue-<identifier>` | 接續對話，回 comment |
| 其他 | — | log + skip |

## 依賴

- Python 3.10+（WSL 預設 ubuntu 有）
- `aiohttp`, `pyyaml`, `python-dotenv`
- hermes CLI 已裝
- Linear personal API key（可讀寫 issue / comment）

## License

MIT
