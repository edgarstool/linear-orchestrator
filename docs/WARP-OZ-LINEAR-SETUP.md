# Warp Oz × Linear 設定（Windows）

參考官方文件：
- [Integrations Overview](https://docs.warp.dev/platform/integrations/)
- [Linear integration](https://docs.warp.dev/agent-platform/cloud-agents/integrations/linear/)
- [Integration setup (CLI)](https://docs.warp.dev/reference/cli/integration-setup/)

## 需求（官方）

- Warp **團隊**成員
- **Build / Max / Business** 方案 + **≥20 credits**
- Warp 登入 email 與 Linear workspace 相同
- 第一次觸發需授權 **GitHub App**

## 建議流程（人類友善）

### A. 用網頁精靈（推薦）

1. 開 [oz.warp.dev](https://oz.warp.dev)
2. 建立 **Environment**：
   - Docker：`python:3.11`
   - Repo：`Edgar-s-Tool/linear-orchestrator`
   - Setup：`pip install -e .`
3. 授權 GitHub（Warp GitHub App）
4. 建立 **Linear integration** → 瀏覽器安裝 **Oz** app

### B. 用 Warp 終端機 CLI（需在 Warp app 內執行）

`oz.cmd` 在一般 PowerShell 可能無輸出或卡住；請在 **Warp 終端機**執行：

```text
oz environment create \
  --name edgar-linear-dev \
  --docker-image python:3.11 \
  --repo Edgar-s-Tool/linear-orchestrator \
  --setup-command "pip install -e ."

oz integration create linear --environment <ENV_ID>
```

## 瀏覽器 assign 測試

1. 確認 Linear Settings → Agents 有 **Oz**
2. 開測試 issue：[EDG-288](https://linear.app/edgarstool/issue/EDG-288/test-oz-assign-smoke-test)
3. **Delegate → Oz**（或 comment `@Oz`）
4. 預期：Oz ack → task list → 可能開 PR / session link

## 目前狀態（2026-07-01，已自動設定）

| 項目 | 狀態 |
|------|------|
| Warp 登入 | ✅ edgar@edgarbeyourself.com / 團隊 edgarstool |
| API 金鑰 | ✅ 已寫入 Windows 使用者環境變數 `WARP_API_KEY` |
| Environment `edgar-linear-dev` | ✅ `gMtdQHl184AFGV1DgM8eLk` |
| Linear integration | ✅ 已連線，綁定 `edgar-linear-dev` |
| 一鍵腳本 | `setup-warp-api.ps1`、`ask-warp.ps1`、`watch-warp-run.ps1`、`install-warp-skills.ps1` |
| Warp 技能 | `skills/warp-oz-{cursor,router,deploy,monitor,github-actions,linear}/` |

### 德德怎麼用（不用懂 API）

```powershell
cd V:\projects\linear-orchestrator

# 檢查一切是否正常
.\scripts\setup-warp-api.ps1

# 叫 Warp 做事（例：掃描 linear-orchestrator）
.\scripts\ask-warp.ps1 -Prompt "讀 README 並用三句話摘要這個專案在做什麼"
```

或在 **Linear** 開 issue → 右側 **Delegate → Oz**（或留言 `@Oz`）。
