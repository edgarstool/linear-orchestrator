# 資料來源與 API 參考

`scripts/standup.py` 依序查詢三個來源。每個來源都可獨立關閉（`--no-*`），缺 token 時會優雅降級並在報告末尾附「資料來源備註」。

## 1. Linear（GraphQL）

- Endpoint：`https://api.linear.app/graphql`
- 認證：header `Authorization: <LINEAR_API_KEY>`（personal key `lin_api_...`，直接放值、不加 `Bearer`）。
- 查詢：抓 `viewer.assignedIssues`（指派給 key 擁有者的 issue，最多 100 筆，依 `updatedAt` 排序）。

擷取欄位：

```graphql
query Standup {
  viewer {
    name
    assignedIssues(first: 100, orderBy: updatedAt) {
      nodes {
        identifier title url updatedAt completedAt
        state { name type }
        labels { nodes { name } }
        inverseRelations { nodes { type relatedIssue { identifier state { type } } } }
      }
    }
  }
}
```

### state.type 分類

Linear 的 workflow state 有穩定的 `type` 列舉，跨團隊一致（state 的顯示名稱則不一定），所以分類一律看 `type`：

- `completed` / `canceled` → 昨日完成（需 `completedAt` 或 `updatedAt` 落在窗口內）
- `started` → 今日計畫（進行中，優先排序）
- `unstarted` → 今日計畫（待辦）
- `backlog` / `triage` → 不進 standup

### Blocker 判定

- `inverseRelations` 中 `type == "blocks"` 表示「relatedIssue 卡住這個 issue」；只有當卡住方 state 尚未 `completed/canceled` 才算有效 blocker。
- 或 issue 帶有名稱含 `block` 的 label。

## 2. Git

- 以 `git -C <repo> log --since=<cutoff> --pretty=... --no-merges` 抓窗口內 commit。
- 用 unit separator（`\x1f`）分隔 `%H %an %ad %s`，避免 subject 內含空白/管線字元造成解析錯亂。
- 非 git 目錄或 git 不存在時回傳空清單 + 備註，不中斷。

## 3. mem0（REST）

- Endpoint：`POST {MEM0_BASE_URL}/v1/memories/search/`（預設 base `https://api.mem0.ai`）。
- 認證：header `Authorization: Token <MEM0_API_KEY>`。
- Body：`{"query": ..., "user_id": ..., "limit": 5}`。
- 回應相容兩種格式：直接的 list，或 `{"results": [...]}`；每筆記憶文字取 `memory` / `text` / `content` 其一。

> 若改用自架 mem0 OSS 或 Honcho，只需覆寫 `MEM0_BASE_URL`（與必要的 header），或改 `collect_memories`。

## 排程建議

搭配 repo 既有的 Windows scheduled task / systemd 模式，可每天早上跑：

```bash
python skills/daily-standup/scripts/standup.py --window-hours 24 --output standup-$(date +%F).md
```

或直接貼回某張追蹤用的 Linear issue：

```bash
python skills/daily-standup/scripts/standup.py --post-to-issue <ISSUE_ID>
```
