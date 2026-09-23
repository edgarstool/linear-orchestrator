# Runtime 狀態持久化與恢復（EDG-86）

本文件說明 linear-orchestrator 的**可變 runtime 狀態**放在哪裡、當機／部署失敗後怎麼恢復、
以及備份與刪除的預期行為。回滾指南的痛點是「本地 JSON 狀態是單點故障」，這裡把關鍵狀態統一收進
一個可備份、可還原的 SQLite state root。

## 1. 可變狀態盤點

| 狀態 | 位置 | 關鍵性 | 說明 |
|---|---|---|---|
| session 對應（Linear issue / agent session → hermes session） | state root 內 `sessions.db` 的 `sessions` 表 | **關鍵** | 遺失會讓對話延續斷掉，agent 重新問一次已問過的事 |
| delivery 紀錄（去重、狀態、延遲） | `sessions.db` 的 `deliveries` 表 | **關鍵** | 遺失會導致重複處理同一個 webhook、dashboard 統計歸零 |
| webhook payload（`/retry`、恢復重播用） | `sessions.db` 的 `payloads` 表 | **關鍵** | EDG-86 之前是 `payloads/*.json` 散落檔案，現已收進 DB |
| in-flight 背景任務（`app["_pending"]`） | 記憶體 | 中 | 程序死掉就沒了；改由 `queued` / `running` delivery 狀態在啟動時重建 |
| SSE 訂閱者（`Broadcaster`） | 記憶體 | 低 | 純推播，client 會自動重連，不需要持久化 |
| PID 檔 | Linux `<repo>/.pid`；Windows `G:\AI_WORK_512\run\linear-orchestrator\orchestrator.pid` | 低 | 純程序控制，可刪 |
| 執行日誌 | Linux `<repo>/orchestrator.log`；Windows `G:\AI_WORK_512\run\linear-orchestrator\orchestrator.{out,err}.log`；systemd 走 journal | 低 | 只作除錯，可刪 |
| hermes 自己的 session 內容 | hermes 端（本服務只送 `--continue <session_key>`） | 外部 | 不在本 repo 的備份範圍 |

## 2. State root 解析順序

1. `LINEAR_ORCHESTRATOR_STATE_DIR`（**部署建議明確指定**）
2. `$XDG_DATA_HOME/linear-orchestrator`
3. `~/.local/share/linear-orchestrator`（舊預設，升級時仍可讀）

備份目錄預設 `<state root>/backups`，可用 `LINEAR_ORCHESTRATOR_BACKUP_DIR` 指到別的磁碟／掛載點。

Windows 原生啟動腳本已自動帶入：

- state：`G:\AI_WORK_512\state\linear-orchestrator`
- backups：`G:\AI_WORK_512\backups\linear-orchestrator`

> 注意：`G:\AI_WORK_512\run\linear-orchestrator` 是**可丟棄**的 run 目錄（pid / log），
> 和上面的 state 目錄是兩回事，不要混在一起清。

相關環境變數：

| 變數 | 預設 | 用途 |
|---|---|---|
| `LINEAR_ORCHESTRATOR_STATE_DIR` | 見上方解析順序 | 狀態根目錄 |
| `LINEAR_ORCHESTRATOR_BACKUP_DIR` | `<state root>/backups` | 快照目錄 |
| `STATE_BACKUP_INTERVAL_SEC` | `86400` | 自動快照間隔，`0` 關閉 |
| `STATE_BACKUP_KEEP` | `7` | 保留幾份快照 |
| `STATE_AUTO_RESUME` | `1` | 啟動時是否自動重播被中斷的 delivery |
| `STATE_RESUME_MAX_AGE_SEC` | `3600` | 超過這個年紀的中斷事件只標記不重播 |
| `STATE_RESUME_LIMIT` | `20` | 單次啟動最多重播幾筆 |
| `PAYLOAD_RETENTION_DAYS` | `7` | payload 保留天數 |

## 3. 持久化與恢復是怎麼運作的

寫入面：

- SQLite 走 `journal_mode=WAL` + `synchronous=FULL`，webhook 被接受時狀態已落地才回 Linear。
- 收到可處理的事件時，**先寫 `payloads` + `deliveries(status=queued)`，再回 202**，
  背景開始跑時轉為 `running`，結束時轉成 `written` / `hermes_fail` / `write_fail` / `exception` 等終態。

恢復面（服務啟動時自動執行，見 `linear_orchestrator/server.py` 的 `recover_state`）：

1. 把舊版留下的 `payloads/*.json` 匯入 DB（冪等，重跑不會重複）。
2. 把仍卡在 `queued` / `running` 的 delivery 標記為 `interrupted`——這些就是當機／部署中斷掉的。
3. 對還在 `STATE_RESUME_MAX_AGE_SEC` 內、且有存 payload 的中斷事件，以 `resume-<原 id>-<ts>` 重新排程處理。
4. 摘要寫入 log、`_recovery` delivery 紀錄，以及 `GET /state` 的 `last_recovery` 欄位。

## 4. 操作流程

### 4.1 查看目前狀態

```bash
curl -s http://*********:8645/state | jq
# 或不需要服務在跑：
python3 -m linear_orchestrator.state_cli inspect
```

### 4.2 部署前備份（建議寫進部署腳本）

```bash
python3 -m linear_orchestrator.state_cli backup --keep 7
# 或 Linux/WSL 排程用：
KEEP=14 bash scripts/backup-state.sh
```

服務在跑也可以直接呼叫 `curl -s -X POST http://*********:8645/state/backup`。

### 4.3 當機或重啟後

正常情況**不需要人工介入**：服務啟動時會自己跑恢復流程。確認方式：

```bash
curl -s http://*********:8645/state | jq '.last_recovery, .counts, .pending_deliveries'
```

若 `STATE_AUTO_RESUME=0`（關閉自動重播），手動補送：

```bash
python3 -m linear_orchestrator.state_cli pending          # 看有哪些卡住
curl -s -X POST http://*********:8645/retry/<delivery_id> # 逐筆重播
```

### 4.4 部署失敗 / 狀態毀損後回復

```bash
# 1. 停服務（Windows: Stop-LinearOrchestrator.ps1 / Linux: scripts/stop.sh 或 systemctl stop）
# 2. 挑一份快照並先驗證
python3 -m linear_orchestrator.state_cli verify --from <backup_dir>/sessions-<stamp>.db
# 3. 還原（現有 DB 會先被複製成 sessions.db.pre-restore-<epoch>，不會被無聲蓋掉）
python3 -m linear_orchestrator.state_cli restore <backup_dir>/sessions-<stamp>.db --force
# 4. 啟動服務；啟動時的恢復流程會重播近期被中斷的 delivery
```

搬機器 / 換 VPS：把整個 state root 目錄複製過去（或帶一份快照過去 `restore`），
再設定相同的 `LINEAR_ORCHESTRATOR_STATE_DIR` 即可，不需要重建 session 對應。

## 5. 備份／恢復預期（操作者請看這段）

**必須備份：**

- state root 下的 `sessions.db`（唯一的真實來源）
- `backups/sessions-*.db` 快照（若快照目錄與 state root 不同磁碟，兩邊都要進備份策略）

**可以安全刪除：**

- PID 檔（`.pid` / `orchestrator.pid`）
- 日誌（`orchestrator.log`、`orchestrator.out.log`、`orchestrator.err.log`、journal）
- `G:\AI_WORK_512\run\linear-orchestrator\` 整個 run 目錄
- 舊的 `payloads/*.json`（已匯入 DB 後；可用 `state_cli import-legacy --delete-source` 確認匯入再刪）
- 超過保留期的 `backups/sessions-*.db`（`--keep` / `STATE_BACKUP_KEEP` 會自動輪替）
- `sessions.db.pre-restore-*`（確認還原正確後）
- `.venv/`、`__pycache__/`（可重建）

**不要單獨刪除：**

- `sessions.db-wal`、`sessions.db-shm`：這是 SQLite WAL 的一部分，服務執行中刪掉會造成資料遺失或毀損。
  要複製檔案的話，先停服務或改用 `state_cli backup`（線上快照，會處理 WAL）。
- `sessions.db` 本體：刪掉等於失去 session 延續、去重紀錄與可重播的 payload。

**保留期預期：**

- payload 預設保留 7 天（`PAYLOAD_RETENTION_DAYS`），過期後 `/retry` 該筆會回 404，屬正常行為。
- `sessions` / `deliveries` 不自動刪除；長期成長很慢（每筆 delivery detail 上限 2000 字元）。
- 自動快照預設每日一份、保留 7 份。

## 6. 相關程式碼

- `linear_orchestrator/state.py` — state root / db / backup 路徑解析
- `linear_orchestrator/session.py` — SQLite schema、payload 儲存、`mark_interrupted`、線上備份
- `linear_orchestrator/server.py` — `recover_state`、`/state`、`/state/backup`、備份與清理背景任務
- `linear_orchestrator/state_cli.py` — `inspect` / `backup` / `restore` / `verify` / `import-legacy` / `prune` / `pending`
- `scripts/backup-state.sh` — 排程備份用
