"""Configuration rules, bounded plans, and independent verification."""

import copy
from http.cookies import CookieError, SimpleCookie

from .contracts import ACTIONS, JsonObject
from .network import NETWORK_ERRORS, Scope


def extract_candidates(evidence: JsonObject) -> list[JsonObject]:
    """Configuration observations only; absence is never an exploit claim."""
    headers = {k.lower(): v for k, v in evidence["headers"]}
    if not 200 <= evidence["status"] < 300 or "text/html" not in headers.get("content-type", "").lower():
        return []
    result = []

    def add(code: str, title: str, detail: str, fix: str, cookie: str = "") -> None:
        result.append(
            {
                "code": code,
                "title": title,
                "detail": detail,
                "severity": "low",
                "fix": fix,
                "cookie": cookie,
                "evidence_ids": [evidence["id"]],
            }
        )

    if not headers.get("content-security-policy", "").strip():
        add(
            "csp_missing",
            "未設定 Content-Security-Policy",
            "HTML 回應未提供 CSP；這是防護設定缺口，不能單獨證明 XSS。",
            "依資源需求建立 CSP，先以 Report-Only 觀察，再逐步啟用。",
        )
    if headers.get("x-content-type-options", "").lower().strip() != "nosniff":
        add(
            "nosniff_missing",
            "未啟用 nosniff",
            "X-Content-Type-Options 未設為 nosniff。",
            "回傳 X-Content-Type-Options: nosniff 並設定正確 Content-Type。",
        )
    # Only session/auth-like names: analytics cookies need not be HttpOnly.
    for key, value in evidence["headers"]:
        if key.lower() != "set-cookie":
            continue
        parsed = SimpleCookie()
        try:
            parsed.load(value)
        except CookieError:
            continue
        for name, cookie in parsed.items():
            if not any(part in name.lower() for part in ("session", "auth", "sid", "token")):
                continue
            if not cookie["httponly"]:
                add(
                    "cookie_httponly",
                    f"{name} 未設定 HttpOnly",
                    "疑似工作階段 Cookie 可被 JavaScript 讀取；用途仍需人工確認。",
                    "若為工作階段 Cookie，啟用 HttpOnly。",
                    name,
                )
            if not cookie["secure"]:
                add(
                    "cookie_secure",
                    f"{name} 未設定 Secure",
                    "疑似工作階段 Cookie 未限制於 HTTPS 傳輸。",
                    "啟用 HTTPS，並為工作階段 Cookie 設定 Secure。",
                    name,
                )
            if not cookie["samesite"]:
                add(
                    "cookie_samesite",
                    f"{name} 未明確設定 SameSite",
                    "Cookie 的跨站行為依瀏覽器預設；不代表已證明 CSRF。",
                    "依登入流程設定 SameSite=Lax 或 Strict。",
                    name,
                )
    return result


def validate_plan(data: JsonObject) -> list[JsonObject]:
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 3:
        raise ValueError("Planner 必須回傳 1–3 個 tasks。")
    seen = set()
    clean = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("action") not in ACTIONS:
            raise ValueError("Planner 使用未允許的 action。")
        action = task["action"]
        if action in seen or set(task) - {"action", "reason"}:
            raise ValueError("Planner 不可重複任務或新增工具參數。")
        reason = task.get("reason")
        if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
            raise ValueError("Planner reason 格式不正確。")
        seen.add(action)
        clean.append({"action": action, "reason": reason})
    return clean


def verify(scope: Scope, candidates: list[JsonObject]) -> tuple[list[JsonObject], list[JsonObject]]:
    """Re-fetch independently; model output cannot set a verification status."""
    if not candidates:
        return [], []
    reports = copy.deepcopy(candidates)
    try:
        fresh = scope.fetch()
        evidence = [fresh]
        matches = {(c["code"], c["cookie"]) for c in extract_candidates(fresh)}
        usable = 200 <= fresh["status"] < 300 and any(
            k.lower() == "content-type" and "text/html" in v.lower() for k, v in fresh["headers"]
        )
        for finding in reports:
            key = (finding["code"], finding["cookie"])
            finding["status"] = (
                ("confirmed" if key in matches else "not_reproduced") if usable else "inconclusive"
            )
            finding["verification"] = "獨立 GET 重測：" + finding["status"]
            finding["evidence_ids"].append(fresh["id"])
    except NETWORK_ERRORS:
        evidence = []
        for finding in reports:
            finding["status"] = "inconclusive"
            finding["verification"] = "重測連線失敗，保留原始觀察。"
    return reports, evidence
