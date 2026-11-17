"""Shared JSON contracts and registered actions; no network or storage effects."""

from datetime import datetime, timezone
from typing import Any, Protocol, TypeAlias

JsonObject: TypeAlias = dict[str, Any]

ACTIONS = {
    "scan": ("網站掃描", "讀取指定頁面，檢查 HTML 回應的安全標頭。"),
    "command": ("執行指令", "以固定 Python 子程序檢查 TLS 憑證與連線。"),
    "request": ("送出請求", "重讀指定頁面，分析 Set-Cookie 安全屬性。"),
}


class ModelClient(Protocol):
    """Common boundary for Codex CLI and compatible HTTP model backends."""

    name: str

    def ask(self, role: str, data: JsonObject) -> JsonObject:
        """Return structured output or raise a visible backend error."""
        ...


def now() -> str:
    """Return the UTC timestamp used by persisted report contracts."""
    return datetime.now(timezone.utc).isoformat()
