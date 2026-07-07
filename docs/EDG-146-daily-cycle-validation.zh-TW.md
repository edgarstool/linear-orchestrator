# EDG-146：驗證新版骨架是否適合日常工作循環

驗證基準：**EDGAR-OS v1.0**（唯一地形基準）
本文件對齊 repo 內 canonical 規則來源：[`AGENTS.md`](../AGENTS.md) 與 [`.github/instructions/edgar-os.instructions.md`](../.github/instructions/edgar-os.instructions.md)。

## 0. 本次驗證邊界與限制（Known Limits）

- 本次執行環境為 Linux sandbox，**無本機檔案系統存取能力**。
- 固定入口檔案皆回報 **Missing**（未掛載，未自行建立替代路徑）：
  - `G:\Agent-KB\DAILY\RECENT.md`
  - `G:\Agent-KB\DAILY\LEARNINGS.md`
  - `G:\Agent-KB\RULES.md`
  - `G:\Agent-KB\PLAYBOOKS\AGENT-SKILLS-SCAN-MAP.md`
- 因此本驗證屬於「**規則層 / 地形層桌面推演 + repo 內文件驗證**」，非本機實體資料的實跑。實體落點試跑需在具本機存取能力的 session 補做（見 §7）。
- 未掃描、未索引、未引用任何 secrets-like 路徑。未搬移任何實體資料。

## 1. Source of Truth 與地形基準對齊

以 `AGENTS.md` 的優先序為準：
1. 當前使用者明確指令
2. App 內全域指令
3. repo-local `AGENTS.md`
4. `G:\Agent-KB` orientation files
5. active workspace code / tests / docs
6. 舊記憶與舊聊天

**判定**：Linear 舊註記（例如 `D:\` = EDGAR_DATA、`~/AI-Repos`、`C:\Users\EdgarsTool\Projects` 當 root 等）與現行 canonical 不一致者，一律視為 `historical-record` / `superseded`，**不當 current authority**。current authority = 本 repo 的 EDGAR-OS v1.0 規則。

## 2. EDGAR-OS v1.0 canonical 地形（現行）

| 用途 | Canonical | Physical / fallback |
|------|-----------|---------------------|
| Windows 使用者 / agent 設定層 | `C:\Users\EdgarsTool` | — |
| repo / project 實作主場 | `V:\projects` | — |
| runtime / cache / tmp / heavy storage | `G:\AI_WORK_512` | — |
| Agent-KB（規則母本） | `G:\Agent-KB` | `G:\AgentKB\Agent-KB` |
| Obsidian（人類長期知識庫） | `G:\Obsidian\Edgar'sObsidianVault` | `G:\AgentKB\Obsidian\Edgar'sObsidianVault` |

Deprecated（不作正式入口、不寫新檔）：`D:\`、`C:\Users\EdgarsTool\Projects\<name>` 當 repo 主場。

## 3. 多 AI 協作區域守則（對應 EDG-163）

每區以「放什麼 / 不放什麼 / 誰使用」定義，給人工與所有 AI 共同遵守。

### 3.1 主場區 — `V:\projects`
- **放**：正式 code、可交付的 project work、可進版控的檔案。
- **不放**：runtime / cache / 大型可重建產物、一次性草稿、規則母本、個人筆記。
- **誰用**：人工 + 主要 AI + 輔助 AI（凡是要 commit 的正式產出）。

### 3.2 heavy storage / 試煉區 / 孵化區 — `G:\AI_WORK_512`
- **放**：runtime、cache、models、generated artifacts、backups、暫存與可重建大型資料。
- **不放**：唯一真相來源、規則母本、需長期保存且無法重建的手寫知識。
- **誰用**：所有 AI 的執行過程與暫存產物；可隨時清空重建。

### 3.3 知識母本區 — `G:\Agent-KB`
- **放**：穩定、已定稿的 agent 規則母本（RULES、PLAYBOOKS、DAILY orientation）。
- **不放**：一次性草稿、未定稿實驗、runtime、個人主觀筆記。
- **誰用**：agent 進任務前**只讀**；升格為規則母本需人工/Strategy 明確決策後回寫。

### 3.4 筆記區 — `G:\Obsidian\Edgar'sObsidianVault`
- **放**：人類長期知識沉澱、主觀思考、跨專案心得。
- **不放**：agent 規則母本、runtime、正式 code。
- **誰用**：偏人工；AI 回寫知識前需明確標記來源與時間。

### 3.5 封存區
- **條件**：任務結束、被 supersede、或轉為 historical-record 時封存。
- **放**：已交接、不再變動的內容；保留可追溯性但不再當 current authority。

### 3.6 交接與封存規則
- 一次性草稿**不得**自動升格為規則母本（`G:\Agent-KB`）。
- 同一份資訊避免在多區平行維護；以「單一真相 + 其他區引用」為原則。
- AI **不得**自行創造新的 canonical 路徑或新地形命名系統。

## 4. 代理輸出落點地圖（對應 EDG-77）

| 輸出類型 | 產生者 | 預設落點 | 回寫 / 封存路徑 |
|----------|--------|----------|-----------------|
| 正式 code / PR | 人工、主要 AI | `V:\projects\<repo>` | 進版控 → merge → 封存於 git 歷史 |
| 任務執行暫存 / log / cache | 所有 AI | `G:\AI_WORK_512` | 可重建者不回寫；有價值結論回寫 Agent-KB 或 Obsidian |
| 大型 artifact / model / backup | 所有 AI | `G:\AI_WORK_512` | 不進版控；必要時記錄索引 |
| 已定稿規則 / playbook | 人工 + Strategy 決策後 | `G:\Agent-KB` | 由草稿升格前需明確決策 |
| 個人知識 / 心得 | 人工（AI 輔助） | `G:\Obsidian\...` | 長期沉澱，標記來源 |
| 任務追蹤 / 驗證迴圈 | 所有協作者 | Linear | 完成後標記；規則結論再回寫 Agent-KB |

**邊界說明一句話版**：`V:\projects` 只承接正式 code；`G:\AI_WORK_512` 只承接可重建 runtime/heavy；`G:\Agent-KB` 只承接穩定規則母本；`G:\Obsidian` 偏個人知識；Linear 是任務帳本，不是規則權威。

## 5. 常見錯放情境與修正方式

| 錯放情境 | 風險 | 修正 |
|----------|------|------|
| 把 repo 建在 `C:\Users\EdgarsTool\Projects\<name>` | 混入設定層、非主場 | 移到 `V:\projects\<name>` |
| 在 `D:\` 建新入口或寫新檔 | 使用 deprecated 地形、混線 | 停止；改用 `V:\` / `G:\` canonical |
| runtime / cache 塞進 `V:\projects` 並 commit | 污染 source tree | 移到 `G:\AI_WORK_512`；加入 `.gitignore` |
| 一次性草稿寫進 `G:\Agent-KB` | 假規則被當母本 | 退回暫存區；經決策才升格 |
| 同資訊在 Agent-KB 與 Obsidian 平行維護 | 雙份漂移 | 定單一真相，另一邊改為引用 |
| AI 自建新資料夾 / 新命名 | 平行結構失控 | 禁止；只用既定 canonical 路徑 |

## 6. 最小試跑（1 正式工作 + 1 短測試 + 1 知識回寫）

因無本機存取，以下為**在 repo 內可實跑**的對應案例，作為地形規則的可行性驗證；本機實體落點於 §7 補做。

- **正式工作案例**：本次 EDG-146 交付文件本身。落點 = repo（`V:\projects` 類比，正式 code/docs 進版控）。→ 落點穩定、可 commit、可 PR。✅
- **短測試案例**：repo 既有 `tests/test_parser.py`、`tests/test_writer.py` 為「短測試」代表；測試產物屬 runtime，不進版控。→ 測試/暫存與正式產出邊界清楚。✅
- **知識回寫案例**：本文件 §3–§5 的區域守則與錯放修正，屬「可升格為規則母本」的候選；依規則**不自動**寫入 `G:\Agent-KB`，而是先在 repo 定稿、經 Strategy/人工決策後再回寫。→ 回寫路徑清楚、避免草稿誤升格。✅

## 7. 待補（需本機存取能力的 session）

- 在具 `G:\`、`V:\` 存取能力的 session，實跑三個真實輸出案例，逐一驗證實體落點與回寫路徑。
- 讀取四個固定入口檔案，確認與本文件規則一致；若有落差回寫修正。
- 驗證內容持續累積後 `G:\Agent-KB` 是否仍維持「只放穩定母本」不膨脹。

## 8. 結論（Acceptance Criteria 對應）

- **是否適合作為日常預設**：**適合作為日常預設地形**，前提是 §7 的本機實跑補完。規則層清楚、邊界可用、與 repo canonical 一致。
- **穩定落點**：`V:\projects`（正式產出）、`G:\AI_WORK_512`（runtime/heavy）、`G:\Agent-KB`（規則母本）、`G:\Obsidian`（個人知識）、Linear（任務帳本）—— 五個落點各有單一職責，落點穩定。
- **邊界清楚度**：主場區 vs heavy storage vs 規則母本 vs 筆記區 界線明確；判準是「可否重建 / 是否已定稿 / 是否需進版控」。
- **最易混線處**：
  1. `G:\AI_WORK_512`（runtime）與 `V:\projects`（正式）之間 —— 大型產物易誤 commit。
  2. 草稿 → `G:\Agent-KB` 規則母本的升格界線 —— 易把一次性內容當母本。
  3. `G:\Agent-KB` 與 `G:\Obsidian` 的知識歸屬 —— 規則母本 vs 個人知識易平行維護。
- **需調整的區域與規則**：
  1. 為「升格為規則母本」補上明確 gate（誰決策、什麼條件），避免草稿誤升格。
  2. 為 `V:\projects` 補 `.gitignore` 慣例，擋 runtime/artifact 污染。
  3. 封存區需補明確物理位置與封存判準（目前僅有條件，缺 canonical 落點）。

## 9. 風險

- 比喻（異世界基地/公會等世界觀層）好記但不可取代實作落點；本文件以實體 canonical 路徑為準，世界觀僅作記憶輔助。
- 長期累積後 `G:\Agent-KB` 仍可能膨脹失控 → 需定期巡檢與封存（見 §7、§8 調整項）。
