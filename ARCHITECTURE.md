# 設計與驗證

## 2026-11-17 Clean Code 整理

本次依 `clean-code` 與 `ecc:python-patterns` 重構 `sentinel/core.py` 和 `sentinel/web.py`。目的是讓一個方法只處理一個階段，並保留既有 `audit()` 參數、HTTP 介面、事件快照與報告欄位。

### 檢查結果與處理方式

| 優先度 | 原有問題 | 處理方式 |
| --- | --- | --- |
| 高 | `audit()` 有 124 行，混合範圍驗證、規劃、工具併行、AI 註解、重測與結束判定 | 由私有 `_AuditSession` 管理單一任務的狀態，拆分各階段方法，公開入口保留 22 行 |
| 高 | Web `do_POST()` 有 76 行，混合授權、內容解析、驗證、排隊與背景錯誤處理 | 分開請求解析、授權、啟動任務與背景執行方法 |
| 高 | Web `do_GET()` 有 40 行，混合靜態檔案、模型設定與報告匯出 | 拆分設定回應與報告回應，路由只負責選擇處理方式 |
| 中 | 同一組目標、模式、backend 在背景工作中反覆以散開參數傳遞 | 使用私有且不可變的 `_AuditRequest` 與 `_AuditOptions` 描述資料，不擴充公開 API |
| 低 | 部分方法因結果字典而略長 | 保留可直接閱讀的資料字典，沒有為行數新增抽象層或插件系統 |

既有耦合方向維持為 Web 與 CLI 呼叫 core，core 使用 checks、network 與 ModelClient 介面。私有 session 集中單一任務的 report 和事件回呼，沒有新增持久狀態或跨任務記憶。既有模型 adapter、檢查規則與資料庫格式未改動。

### 複雜度比較

以本機 Python AST 計數估算每個函式的圈複雜度，基準為 1，加上條件、迴圈、例外分支、條件運算式、布林短路與 comprehension 分支。巢狀函式與類別的方法獨立計算，避免重複累計。這是本次前後使用同一算法的估算，沒有使用 Radon 或宣稱為標準工具報告。

| 方法 | 整理前行數 | 整理後行數 | 分支估算前後 |
| --- | --- | --- | --- |
| `audit()` | 124 | 22 | 30 → 2 |
| `Handler.do_GET()` | 40 | 16 | 12 → 6 |
| `Handler.do_POST()` | 76 | 13 | 17 → 4 |

拆出的每個新方法分支估算不超過 7。這表示分支已分配到各自的職責，並非整個系統的判斷總量或執行時間下降。`make_server()` 仍包含巢狀 Handler 類別定義，不能把整段文字行數視為同一個執行方法的複雜度。

### 實際驗證

整理前先執行既有測試，結果為 **32 passed**。補上 planner、worker、verifier 失敗與部分工具失敗的行為案例後，結果為 **36 passed**。核心流程拆分後與 Web 拆分後，分別重跑全部測試，兩次皆為 **36 passed**。

最後加入 HTTP 驗證、同時只執行一項任務、背景錯誤後釋放鎖的測試：

- `python -m pytest -q --basetemp=../../work/clean-code-final`：**47 passed**。
- `python -m black --check app.py sentinel tests scripts`：**22 個 Python 檔案通過**。
- 模型註解失敗時仍保留證據，規劃失敗時不啟動工具，背景錯誤後可建立下一項任務。
- AI 分析輸入仍排除網頁本文，事件回呼仍取得獨立快照。

變更檔案為 `sentinel/core.py`、`sentinel/web.py`、新增的 `tests/test_audit_failures.py` 與 `tests/test_web_boundaries.py`，並更新此文件與 `docs/參數與結果參考.md` 的驗證狀態。沒有變更資料庫或覆寫既有 ZIP。本次未重跑真實 Codex、瀏覽器或真實 HTTPS，亦未執行 coverage、Ruff 或 mypy；測試通過不等於所有路徑都已覆蓋。

## 2026-11-17 Safety Guard 整理

本次實際使用 `ecc:safety-guard` 的 Careful 模式，以及 `ecc:python-patterns`。操作範圍為打包腳本、相關測試、`.gitignore`、README 與此文件；沒有刪除既有資料、修改資料庫、停止服務或重新呼叫真實 Codex。

檢查發現前版打包腳本會以 replace 覆寫同名 ZIP，且副檔名清單會收錄未明列的 JSON / TOML 等檔案。這次改為指定根檔案、程式目錄、靜態資產與兩份示範報告的明確收錄規則，並加入 `--list` 唯讀預覽。新 ZIP 預設命名為 `sentinel-mini-safe.zip`；既有目的檔案會拒絕覆寫，輸出不可在專案內，也不可使用非 `.zip` 副檔名。目的檔以 exclusive creation 開啟，避免檢查之後才出現同名檔案時被覆寫。

來源檔與既有 ZIP 保留。只自動清理本次打包函式自行建立的暫存目錄，不清除使用者快取或歷史資料。安全規則不會自動安裝成系統 hook；本次代理依技能行事，打包腳本的拒絕覆寫與收錄限制則有程式與測試實際執行。這仍不是原始碼機密掃描器；若將機密直接寫進被收錄的 Python 檔，需自行移除後再分享。

變更檔案：`scripts/build_release.py`、`tests/test_release.py`、`.gitignore`、`README.md`、`ARCHITECTURE.md`。

本次驗證：

- `python -m pytest -q --basetemp=../../work/safety-guard-check`：**32 passed**。
- `python -m black --check app.py sentinel tests scripts`：**20 個 Python 檔案通過**。
- 新增測試：收錄清單與來源保留、既有 ZIP 保留、非 ZIP / 專案內輸出拒絕、`--list` 不寫入。

以下模組整理與首次建立的紀錄保留為歷史；其中「替換正式 ZIP」的舊打包行為已由本節的拒絕覆寫流程取代。本次未執行 Ruff、mypy、coverage、真實模型或 HTTPS 憑證重測。

## 2026-11-17 專案整理

本次依 `ecc:python-patterns` 整理既有專案，維持 Codex 整合、啟動指令、API 與報告 JSON 欄位。沒有重新掃描外部網站或呼叫真實模型；原本的 Codex 示範報告與本機資料庫保留。

### 模組責任

| 檔案 | 責任 |
| --- | --- |
| `app.py` | 分開解析參數、CLI 匯出、Web server 生命週期 |
| `sentinel/core.py` | 流程編排與登錄工具執行 |
| `sentinel/network.py` | URL 範圍、固定解析 IP、HTTP 證據 |
| `sentinel/checks.py` | 檢查規則、計畫格式驗證、獨立重測 |
| `sentinel/contracts.py` | JSON payload 型別、ModelClient Protocol、action 定義與時間戳 |
| `sentinel/models.py` | 模型工廠與 Compatible API；Codex adapter 維持獨立 |
| `sentinel/store.py` | SQLite 交易、連線釋放與所有未完成紀錄恢復 |
| `sentinel/reporting.py` | Markdown 格式輸出 |
| `scripts/build_release.py` | 專案內的 ZIP 打包入口，不依賴本次工作區名稱 |

以職責拆分取代單一檔案同時控制傳輸、規則與模型；共用 `ModelClient` Protocol 讓流程不依賴特定 backend 類別。保留 `sentinel.core` 的既有匯入，以及 `sentinel.store.markdown` 的相容入口。型別標註描述 JSON 容器與模型介面，不代表已加入每個報告欄位的靜態 schema 驗證。

SQLite 原先使用 Connection 的 context manager 管理交易，但這不會自動關閉連線。現在 `Store.connect()` 在 commit / rollback 後明確 close，並有追蹤連線關閉及回滾的回歸測試。中斷恢復改讀完整紀錄，不再依賴 UI 最近 100 筆的顯示上限。

伺服器使用 context manager 管理 socket；結束時先停止 demo 服務執行緒再關閉。所有 Python 原始碼與測試套用 Black，設定納入 `pyproject.toml`。新增的打包入口先檢查暫存 ZIP 完整性，再替換正式 ZIP；排除本機資料、環境與快取。

### 本次驗證

- 整理前基準：**21 passed**。
- 整理後：`python -m pytest -q --basetemp=../../work/refactor-final`，**27 passed**。
- `python -m black --check app.py sentinel tests scripts`：**19 個 Python 檔案通過**。
- 新增回歸：未知工具 action 拒絕、SQLite 成功/失敗後關閉、交易回滾、歷史顯示範圍外的中斷恢復、CLI 三種狀態的 exit code 與雙格式輸出。

本次沒有執行 Ruff、mypy、coverage 或真實 Codex 重測；下面的真實 Codex 與瀏覽器紀錄是首次建立專案時的驗證，並非本次重新執行的結果。執行階段仍無第三方依賴；Black 與 pytest 只是開發工具。

## 資料流

```text
URL + goal + mode
 → Scope（單一 origin、固定解析 IP）
 → Codex Planner / 規則計畫 → tasks[{action, reason}]
 → action registry → 最多三個工具並行
 → 真實 evidence + candidates → Codex Worker 註解
 → Verifier 新 GET 重測 → Codex 總結
 → report → SQLite 交易快照 → UI / JSON / Markdown
```

HTTP 證據有 id、time、URL、GET、狀態、遮蔽後標頭、最多 128 KiB 本文、雜湊與 IP。truncated 表示截斷；雜湊對應已擷取原始內容，不是整個遠端文件。TLS 證據含固定 argv 與子程序 JSON。Finding 綁定原始與重測 evidence_ids；重測失敗不升級為 confirmed。

LLM 輸出驗證數量、重複 action、欄位與文字長度；無法指定指令、目標或確認狀態。AI 註解另欄保存，UI 以 textContent 呈現外部內容。網站正文不傳模型。

## 主要決策

- 小專案採標準函式庫降低安裝負擔；只監聽 loopback，HTTPServer 不當生產服務。
- Codex 直接沿用既有登入，使用 exec structured output，不需要另外設定模型 API。分析階段不讓 Codex 操作目標，實際工具由 Python 約束。
- 規劃、執行與確認分工；模型說明不能代替真實工具紀錄，confirmed 僅限設定缺口可重現。
- SQLite 每個事件以交易寫入完整快照；中斷任務標記 interrupted，不自動重送。
- 同時一個 audit，內部三個工具並行，避免無界工作佇列。模型呼叫循序、上限 5 次，不隱藏重試或 fallback。
- 不跟隨 redirect、不使用環境代理、不帶認證；僅使用第一個解析 IP，失敗不自動切換。Codex 與 Compatible 模式的錯誤均保留可見狀態。

## 實際套用的 ECC 技能

- `ecc:python-patterns`：模組分工、type hints、dataclass、context manager、明確錯誤處理、I/O thread pool。
- `ecc:python-testing`：核心測試先於實作、本機 fixture、parametrize、mock、成功與失敗路徑測試。
- `ecc:agent-architecture-audit`：交付前檢查工具執行、模型解讀、呈現與持久化邊界。程式 gate action，模型註解不當事實，無隱藏修復或降級。

另查閱本機 `openai-docs` 技能與已安裝 Codex 的 `exec --help`，確認 CLI flags；未把其他產品或 API 的行為推定為本機 CLI 能力。

## 已執行驗證

- Windows / Python 3.14.3：`python -m pytest -q --basetemp=../../work/pytest-check2`，**21 passed**。
- 測試範圍：URL 與 origin、302 停止、非 HTML、Cookie 遮蔽、重測成功/未再現/失敗、Planner schema、完整規則流程、fake Compatible HTTP API、缺設定失敗、fixed fixture、TLS 固定 argv、SQLite 中斷恢復、Markdown escape、Web token / 授權與報告取得、Codex stdin / schema / read-only / CLI 失敗。
- **真實 Codex CLI 端到端測試通過**：對本機 fixture 規劃、執行、分析與確認，結果為 completed；產出 `examples/codex-demo.json` 與 `.md`。沒有使用第三方網站作測試目標。
- 瀏覽器：本機規則任務 completed，5 項可重現設定、3 筆 HTTP 證據，JSON / Markdown endpoint 均 HTTP 200。桌面與 390px mobile emulation 檢查無橫向溢出。

開發期間發現有 Content-Length 的 HTTP 回應會使 HTTPConnection 提早關閉原始 socket，影響 timeout 更新。已改為自行持有 socket、由 HTTPResponse 解析，統一管理關閉時機；有/無 Content-Length 的 fixture 皆通過。

## 尚未驗證與限制

未量測 coverage，未執行真實 HTTPS 憑證端到端測試或效能壓力測試。TLS subprocess 只有 argv mock 測試，不等同真實 TLS 成功。

Codex CLI 相容性以本機可成功執行的版本為準；舊版 flags 可能不同。Codex 150 秒 timeout 與 Compatible 45 秒 timeout 都不是可恢復的持久 job；失敗需重新建立任務。HTTP 本文讀取預算 12 秒、socket timeout 6 秒，不是隔離惡意伺服器的嚴格總時間 sandbox。

Cookie 名稱判斷可能誤判；沒有發現不證明安全。原始本文可能有敏感內容，會保存於本機 SQLite / JSON，遮蔽不是通用 DLP。無多使用者、加密儲存或正式部署設定。
