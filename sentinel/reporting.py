"""Render audit reports without coupling formatting to persistence."""

from .contracts import JsonObject


def markdown(report: JsonObject) -> str:
    def safe(value: object) -> str:
        return str(value).replace("<", "&lt;").replace(">", "&gt;").replace("`", "'")

    lines = [
        "# Sentinel Mini 網站設定檢查報告",
        "",
        f'- 目標：{safe(report["target"])}',
        f'- 說明：{safe(report["goal"])}',
        f'- 模式：{report["mode"]}',
        f'- 狀態：{report["state"]}',
        f'- 開始時間（UTC）：{report["started_at"]}',
        "",
        safe(report["summary"]),
        "",
        "## 執行任務",
        "",
    ]
    for task in report["tasks"]:
        lines.append(f'- {task["title"]} / {task["state"]}：{safe(task["note"])}')
    lines += ["", "## 發現與獨立重測", ""]
    for f in report["findings"]:
        lines += [
            f'### {safe(f["title"])}',
            "",
            f'- 程度：{f["severity"]}',
            f'- 重測：{f["status"]}',
            f'- 說明：{safe(f["detail"])}',
            f'- 建議：{safe(f["fix"])}',
            f'- 證據 ID：{", ".join(f["evidence_ids"])}',
            "",
        ]
    if report.get("ai_summary"):
        lines += ["## AI 補充（不可覆寫工具判定）", "", safe(report["ai_summary"]), ""]
    if report["warnings"]:
        lines += ["## 限制與錯誤", "", *["- " + safe(w) for w in report["warnings"]], ""]
    lines += ["## 證據索引", "", "完整回應標頭、內容與雜湊請見 JSON 匯出；Cookie 值已遮蔽。", ""]
    for e in report["evidence"]:
        lines.append(f'- {e["id"]} / {e["kind"]} / {e["time"]}')
    return "\n".join(lines) + "\n"
