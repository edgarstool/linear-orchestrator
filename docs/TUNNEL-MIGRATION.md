# Tunnel migration: YAML → Token-based (edgar-local-01-tunnel)

最後更新：2026-06-26

## 現況

Linear orchestrator 本身**完全沒事**：
- WSL `0.0.0.0:8645` 正在跑
- `http://127.0.0.1:8645/` 內建 dashboard 可開
- `http://127.0.0.1:8645/healthz` 回 200

**但** Linear webhook 進不來，因為：

1. 你（或另一個 agent）已把 `~/.cloudflared/config.yml` 標記為 DEPRECATED，所有公網路由改由 **token-based tunnel** `edgar-local-01-tunnel` 管理（在 Cloudflare Dashboard 設定，不在本地 YAML）。
2. 在那個 dashboard tunnel 裡，`webhook.whoasked.vip` 還是指向 **localhost:8644**（舊的 hermes gateway），不是 orchestrator 的 8645。
3. hermes gateway 8644 沒在跑，所以 CF 回 502。
4. Linear 註冊的 webhook URL 仍然是 `https://webhook.whoasked.vip/webhooks/linear`。

## 一步修好：改 dashboard 那個 route

1. 開 <https://one.dash.cloudflare.com/> → Networks → Tunnels → **edgar-local-01-tunnel** → Public Hostname
2. 找 `webhook.whoasked.vip` 那條 row（或新增）
3. Service 從 `http://localhost:8644` 改成 **`http://<WSL_IP>:8645`**
4. 存檔，幾秒後 `https://webhook.whoasked.vip/healthz` 應該回 200

> WSL IP 怎麼拿：在 PowerShell 跑 `wsl -d Ubuntu-24.04-G hostname -I`，現在是 `172.30.59.137`（會隨 WSL 重開漂移）。
>
> 想一勞永逸：在 `%USERPROFILE%\.wslconfig` 加 `[wsl2]` `networkingMode=mirrored`，重啟 WSL 後可改寫成 `http://localhost:8645`，永遠不會漂。

## 或者：改 Linear webhook URL 到 `edgars.tools` 子網域

如果你想把整個架構乾淨對齊到 `*.edgars.tools`：

1. 在 dashboard tunnel 加一條新的 public hostname：`webhooks.edgars.tools/linear-orchestrator` → `http://<WSL_IP>:8645`
   - 或選一個你喜歡的全新子網域，例如 `orchestrator.edgars.tools`
2. 用 Linear API 把 webhook URL 改掉：

```bash
# Get your Linear personal API key from https://linear.app/settings/api
KEY="$LINEAR_API_KEY"   # or read from ~/.hermes/.env
WEBHOOK_ID=1b6fd2fd-fde4-44fb-94e7-9ce1ebbb434d
NEW_URL=https://orchestrator.edgars.tools/webhooks/linear
curl -X POST https://api.linear.app/graphql -H "Authorization: $KEY" -H "Content-Type: application/json" \
  -d "{\"query\":\"mutation{ webhookUpdate(id:\\\"$WEBHOOK_ID\\\", input:{ url:\\\"$NEW_URL\\\" }){ success } }\"}"
```

3. orchestrator 不用動，dashboard tunnel 改一條 route 就生效。

## 為什麼我（orchestrator）不能自己加 dashboard route

Cloudflare token-based tunnel 的 ingress 完全在 dashboard 管理，**不能** 用本地 API 改。本地能做的只有：
- 用 cred-file 模式的 tunnel（你舊的 `home-tunnel`，已 DEPRECATED）
- 在那個舊 tunnel 的 YAML 加 ingress + DNS route

如果你想用「自動化加 route 」的路徑，要回去用 cred-file tunnel，不能用 token tunnel。

## 驗證（修好後）

```bash
# 1. 公網 healthz
curl -i https://webhook.whoasked.vip/healthz
# 預期 200 {"ok": true, "ts": ...}

# 2. 簽過的測試 webhook
set -a; . ~/.hermes/.env; set +a   # 載入 LINEAR_WEBHOOK_SECRET
TS=$(($(date +%s)*1000))
BODY="{\"webhookTimestamp\":$TS}"
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$LINEAR_WEBHOOK_SECRET" -hex | awk '{print $NF}')
curl -i -X POST https://webhook.whoasked.vip/webhooks/linear \
  -H "Linear-Signature: $SIG" -H "Content-Type: application/json" --data "$BODY"
# 預期 401 (no event matches) 而非 502
```

## 副作用清單（這次 session 改完還沒回滾的東西）

| Item | 狀態 |
|---|---|
| Linear webhook URL | 維持 `webhook.whoasked.vip/webhooks/linear` |
| Linear webhook signing secret | 已和 orchestrator 的 `LINEAR_WEBHOOK_SECRET` 同步（儲存在 `~/.hermes/.env`）|
| orchestrator 跑在 | `wsl Ubuntu-24.04-G 0.0.0.0:8645` |
| 舊 home-tunnel cloudflared 進程 | 已殺，留 service-based token tunnel |
