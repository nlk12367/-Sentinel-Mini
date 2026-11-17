# Sentinel Mini 開發日誌

Sentinel Mini 是以 Python 實作的網站設定檢查小專案，透過本機 Codex CLI 完成規劃與分析，並由受限工具收集證據及獨立重測。

本目錄按時間記錄設計決策、實作成果、驗證與限制。檔名格式為 `YYYY-MM-DD--NNN-description.md`，`NNN` 為每日重新起算的三位數流水號；既有條目不覆寫。

| 操作 | 指令 |
| --- | --- |
| 新增紀錄 | `$journal <標題>` |
| 搜尋決策 | `$journal search <關鍵字>` |
| 最近紀錄 | `$journal last [N]` |
| 查找相關背景 | `$journal check` |
| 指令說明 | `$journal help` |

使用規範見 `docs/journal/GUIDE.md`。本次僅建立專案日誌，沒有修改 `AGENTS.md` 或 `CLAUDE.md`，也沒有安裝跨對話自動執行機制。
