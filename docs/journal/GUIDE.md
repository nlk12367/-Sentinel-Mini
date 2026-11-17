## 開發日誌

本專案將開發日誌存放於 `docs/journal/`。
條目使用 `YYYY-MM-DD--NNN-description.md` 命名，例如 `2026-11-17--002-sentinel-mini-codex-refactor-safe-release.md`。

### 指令

| 指令 | 用途 |
| --- | --- |
| `$journal` | 依目前對話自動產生標題並寫入紀錄 |
| `$journal <標題>` | 以指定標題寫入紀錄 |
| `$journal search <關鍵字>` | 依檔名與內容搜尋 |
| `$journal last [N]` | 讀取最近 N 筆，預設一筆 |
| `$journal check` | 查找與目前工作相關的決策 |
| `$journal init` | 初始化日誌與選用的專案指引整合 |
| `$journal help` | 顯示指令說明 |

### 使用時機

- 開始工作前，使用 `$journal check` 查找相關背景。
- 做架構決策前，使用 `$journal search <主題>` 查閱既有理由。
- 完成工作後，使用 `$journal` 記錄實際變更、驗證與限制。

### 撰寫規範

- 先讀既有條目，避免重複紀錄。
- 使用繁體中文，以已完成的事實撰寫，說明決策理由。
- 每日流水號從 001 起算，新增條目不得覆寫舊紀錄。
- 摘要維持一至三句；結構化資訊使用表格。
- 區分實際執行的測試、歷史測試與尚未驗證的事項。
- 以反引號標記專案相對路徑，避免複製整段文件或敏感資料。

### 範例

```text
$journal
$journal Codex 整合與驗證
$journal search sqlite
$journal last 3
$journal check
```

這份指引不會自動建立背景 hook，也不保證其他對話自動呼叫技能。只有使用者明確要求跨對話自動檢查時，才另行檢視並更新專案指令。
