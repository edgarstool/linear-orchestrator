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

## 目前狀態（2026-07-01）

- Linear workspace **尚未安裝 Oz**（`list_users` 查無 Oz）
- 需 Edgar 在 oz.warp.dev 或 Warp 終端機完成 environment + integration（會開瀏覽器 OAuth）
