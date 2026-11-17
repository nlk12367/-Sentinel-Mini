# 001 — Sentinel Mini 開發日誌初始化

**Date:** 2026-11-17
**Scope:** Sentinel Mini 專案日誌與使用指引

## Summary

已依使用者要求建立 Sentinel Mini 的專案開發日誌，保存後續可查詢的決策與工作紀錄。此專案以 Python 串接本機 Codex CLI，提供網站設定檢查、獨立重測與證據報告；初始化時已查閱根目錄 `README.md` 及 `ARCHITECTURE.md`，確認目前結構與驗證歷史。

## What changed

| 項目 | 結果與理由 |
| --- | --- |
| `docs/journal/` | 已建立，將日誌歸屬於 Sentinel Mini，而非工作區暫存目錄 |
| `docs/journal/README.md` | 已建立專案介紹、命名與檢索方式 |
| `docs/journal/GUIDE.md` | 已建立繁體中文使用指引與追加規範 |
| 日誌序號 | 已從本日 001 起算；初始化前未發現既有日誌 |
| 專案自動檢查整合 | 未啟用，使用者未要求修改 `AGENTS.md` 或 `CLAUDE.md` |

## Context

既有程式分布於 `sentinel/`，測試位於 `tests/`，開發設定集中於 `pyproject.toml`。日誌補足 `ARCHITECTURE.md` 的時間脈絡，以追加條目保留決策，不改動現有程式、資料庫或交付 ZIP。完整開發回顧記於本日下一筆條目。
