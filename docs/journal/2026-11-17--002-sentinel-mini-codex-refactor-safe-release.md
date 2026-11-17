# 002 — Sentinel Mini 開發與安全整理

**Date:** 2026-11-17
**Scope:** 初版開發、Codex CLI 整合、Python 模組整理、安全打包與驗證回顧

## Summary

已完成以 Python 實作的規劃、工具執行及獨立確認流程，並依使用者後續指示改為直接串接本機 Codex CLI。其後已拆分模組、修正 SQLite 資源管理與中斷恢復，並將打包改為明確收錄及拒絕覆寫，以降低維護成本與誤帶資料的風險。本條目整理本次對話中已完成的工作；寫入日誌時沒有重新執行程式測試。

## What changed

### 需求與決策

| 項目 | 已採用的決策 | 理由與邊界 |
| --- | --- | --- |
| 參考來源 | 僅在線上查看 ARTEX 的 Planner、Worker、finding workflow 與 HTTP 工具程式碼 | 遵守不下載、不 clone 的要求；Python 版本為獨立簡化實作 |
| 執行環境 | Python 3.11+、標準函式庫、本機瀏覽器介面 | 降低安裝負擔；實測環境為 Windows / Python 3.14.3 |
| 預設 AI | 本機 Codex CLI，沿用既有登入 | 回應使用者「直接接 codex 處理」；保留免模型規則模式與選用 Compatible API |
| AI 邊界 | Codex 處理規劃與分析；Python 執行三類登錄工具 | 避免把模型宣稱當成工具證據；不接受模型新增 URL、指令或 payload |
| 確認機制 | 另發 GET 重測，依 code 與 Cookie 名稱比對 | 模型無法自行覆寫 confirmed；狀態僅證明設定觀察可重現 |
| 任務預算 | 同時一項 audit、最多三個工具並行、最多五次循序模型呼叫 | 限制無界佇列與呼叫數；失敗不隱藏重試或降級 |
| 資料持久化 | SQLite 逐事件交易快照 | 保留執行進度；重啟標記 interrupted，不自動重送工具 |
| 安全整理 | Careful 模式與非破壞式打包 | 保留既有資料與 ZIP；技能本身沒有安裝系統 hook |

### 模組與修正

| 檔案或目錄 | 已完成的內容與原因 |
| --- | --- |
| `app.py`、`start.bat` | 提供 CLI 與 Web 啟動；拆分參數解析、匯出及服務生命週期 |
| `sentinel/core.py` | 集中流程編排與工具執行，減少同檔承擔多種職責 |
| `sentinel/network.py` | 管理 URL、固定解析 IP、有限回應讀取；修正 HTTPResponse 與 socket 關閉時機 |
| `sentinel/checks.py` | 分離標頭及 Cookie 規則、計畫驗證與獨立重測 |
| `sentinel/contracts.py`、`sentinel/models.py` | 定義共用 JSON 型別、ModelClient Protocol、action 清單及模型工廠 |
| `sentinel/codex_model.py` | 透過 stdin、JSON schema、ephemeral read-only CLI 呼叫取得結構化輸出，使用 `shell=False` |
| `sentinel/store.py` | 交易完成或失敗後明確關閉連線；中斷恢復涵蓋最近 100 筆之外的紀錄 |
| `sentinel/reporting.py` | 將 Markdown 呈現與資料庫責任分離；保留既有公開匯入相容性 |
| `sentinel/web.py`、`sentinel/static/` | 本機介面、任務歷史、token 與 Host 檢查、證據及報告匯出 |
| `sentinel/demo.py`、`sentinel/tls_probe.py` | 提供測試頁與 fixed 版本，以及固定 argv 的 TLS 子程序 |
| `scripts/build_release.py` | 加入 `--list`；只收錄指定檔案、拒絕覆寫、拒絕專案內輸出及非 ZIP 目的檔 |
| `tests/`、`pyproject.toml` | 增加資源管理、CLI 與打包回歸測試，集中 Black 格式設定 |
| `.gitignore`、`README.md`、`ARCHITECTURE.md` | 更新環境與產物忽略規則、使用方式、決策與驗證限制 |

SQLite 修正的根因是 Connection context manager 只管理 commit / rollback，不會自行 close。中斷恢復原先依 UI 最近 100 筆清單處理，可能漏掉較舊紀錄，因此改為完整恢復查詢。安全打包修正則源自原版以 replace 覆寫同名 ZIP，以及依副檔名收錄未明列檔案的行為。

### 實際驗證歷史

| 階段 | 已執行的驗證 | 實際結果 |
| --- | --- | --- |
| 初版核心 | 本機 HTTP fixture 與核心規則 | 12 項測試通過 |
| Web / Compatible 整合 | 本機假模型 API、歷史恢復、匯出及失敗處理 | 19 項測試通過 |
| Codex adapter | stdin、schema、read-only 與失敗回報 | 累計 21 項測試通過 |
| 真實 Codex 示範 | 對內建 localhost 目標跑完整 AI 流程 | 4 次模型呼叫、completed、5 項可重現設定觀察，無 warnings |
| 瀏覽器 | 示範任務、匯出端點、桌面及 390px mobile emulation | 顯示 5 項觀察、3 筆 HTTP 證據，兩種匯出端點 HTTP 200，無橫向溢出 |
| Python 整理 | `python -m pytest -q --basetemp=../../work/refactor-final` | 27 passed；Black 檢查 19 個 Python 檔案通過 |
| Safety Guard 整理 | `python -m pytest -q --basetemp=../../work/safety-guard-check` | 32 passed；Black 檢查 20 個 Python 檔案通過 |
| ZIP | 完整性檢查及舊 ZIP 雜湊比對 | 新檔打包成功，原 ZIP 內容未變 |
| 本次日誌 | 檢查來源文件、序號及新增文件 | 只寫入日誌，未重跑上述測試 |

真實 Codex 結果保存在 `examples/codex-demo.json` 與 `examples/codex-demo.md`。後續兩次整理沒有重新呼叫真實 Codex，不能將歷史示範等同整理後的模型重測。

### 交付與保留

- 已交付原始 `sentinel-mini.zip`，後續安全版另存為專案上層的 `sentinel-mini-safe.zip`，沒有覆寫舊檔。
- 安全版已收錄 30 個檔案，SHA-256 為 `cf92d08aaba554238ea80aab590ce4affddb3af0cf138fe838e38c7909384595`。
- 保留 `data/runs.sqlite3` 與既有範例；本次日誌沒有修改資料庫或 ZIP。
- 目前打包明確清單未包含 `docs/journal/`，因此本次新增日誌只存在專案來源目錄，既有 ZIP 不含這些條目。

### 未驗證與限制

- 尚未執行真實 HTTPS 憑證端到端測試、效能壓力測試、Ruff、mypy 或 coverage 量測。
- 只檢查指定頁面的安全標頭、疑似工作階段 Cookie 屬性與 TLS 執行觀察；未實作完整滲透測試或全站爬取。
- confirmed 表示設定觀察可重現，不表示漏洞已遭成功利用；Cookie 用途仍需人工確認。
- HTTP 本文會保存在本機，但不送給模型；遮蔽與打包清單都不是通用 DLP 或機密掃描器。
- Codex 相容性依本機已測版本；服務僅供單使用者本機原型，沒有正式部署或多使用者能力。

## Context

此紀錄保存使用者從 Python 小專案、直接接 Codex、程式整理到安全打包的需求演進及其理由，讓後續工作可區分已完成成果與尚未驗證的事項。詳細操作與資料流分別見 `README.md`、`ARCHITECTURE.md`；日誌初始化見 `docs/journal/2026-11-17--001-sentinel-mini-journal-initialized.md`。本次使用 `journal` 技能整理紀錄；歷史工程工作實際使用的 ECC 技能包括 `python-patterns`、`python-testing`、`agent-architecture-audit` 與 `safety-guard`。
