"""Loopback UI/API with same-origin request token and one active audit."""

import json
import secrets
import threading
import traceback
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .contracts import JsonObject, now
from .core import audit
from .models import create_model
from .network import Scope
from .reporting import markdown
from .store import Store

STATIC = Path(__file__).with_name("static")


STATIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


@dataclass(frozen=True)
class _AuditRequest:
    target: str
    goal: str
    mode: str
    backend: str

    @property
    def use_ai(self) -> bool:
        return self.mode == "ai"


def _parse_audit_request(data: JsonObject) -> _AuditRequest:
    if not isinstance(data, dict) or data.get("authorized") is not True:
        raise ValueError("請先確認你有權限檢查此目標。")
    goal = data.get("goal")
    if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 1000:
        raise ValueError("目標說明須為 1–1000 字。")
    if data.get("mode") not in ("rules", "ai"):
        raise ValueError("請選擇正確模式。")
    backend = data.get("backend", "codex")
    if backend not in ("codex", "compatible"):
        raise ValueError("未知模型 backend。")
    return _AuditRequest(data.get("target"), goal, data["mode"], backend)


def _queued_report(request: _AuditRequest, run_id: str) -> JsonObject:
    return {
        "id": run_id,
        "target": request.target,
        "goal": request.goal,
        "mode": request.mode,
        "state": "queued",
        "started_at": now(),
        "tasks": [],
        "evidence": [],
        "findings": [],
        "events": [],
        "warnings": [],
        "summary": "",
    }


def _configured_model_name(backend: str) -> str | None:
    try:
        return create_model(backend).name
    except ValueError:
        return None


def make_server(port: int, store: Store, demo_url: str) -> ThreadingHTTPServer:
    token = secrets.token_urlsafe(32)
    busy = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send(
            self,
            body: JsonObject | list[JsonObject] | bytes,
            status: int = 200,
            content_type: str = "application/json; charset=utf-8",
        ) -> None:
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(body)

        def host_ok(self) -> bool:
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            return self.headers.get("Host") in allowed

        def do_GET(self) -> None:
            if not self.host_ok():
                self.send({"error": "不接受此 Host。"}, 403)
                return
            path = urlsplit(self.path).path
            if path in STATIC_ASSETS:
                name, mime = STATIC_ASSETS[path]
                self.send((STATIC / name).read_bytes(), content_type=mime)
            elif path == "/api/config":
                self.send_config()
            elif path == "/api/runs":
                self.send(store.list())
            elif path.startswith("/api/runs/"):
                self.send_report(path)
            else:
                self.send({"error": "找不到路徑。"}, 404)

        def send_config(self) -> None:
            self.send(
                {
                    "token": token,
                    "demo_url": demo_url,
                    "model": _configured_model_name("compatible"),
                    "codex": _configured_model_name("codex"),
                }
            )

        def send_report(self, path: str) -> None:
            parts = path.strip("/").split("/")
            report = store.get(parts[2])
            if not report:
                self.send({"error": "找不到任務。"}, 404)
            elif len(parts) == 4 and parts[3] == "markdown":
                self.send(markdown(report).encode("utf-8"), content_type="text/markdown; charset=utf-8")
            elif len(parts) == 3:
                self.send(report)
            else:
                self.send({"error": "找不到路徑。"}, 404)

        def is_authorized_post(self) -> bool:
            origin = self.headers.get("Origin")
            valid_origins = {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }
            return (
                self.host_ok()
                and self.headers.get("X-Sentinel-Token") == token
                and (not origin or origin in valid_origins)
            )

        def read_audit_request(self) -> _AuditRequest:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise ValueError("請求大小不正確。")
            request = _parse_audit_request(json.loads(self.rfile.read(size)))
            if request.use_ai:
                create_model(request.backend)
            Scope(request.target)  # Execution resolves and pins its own scope.
            return request

        def do_POST(self) -> None:
            if not self.is_authorized_post():
                self.send({"error": "請重新整理本機介面。"}, 403)
                return
            if self.path != "/api/runs":
                self.send({"error": "找不到路徑。"}, 404)
                return
            try:
                request = self.read_audit_request()
            except (ValueError, OSError, TypeError) as exc:
                self.send({"error": str(exc)}, 400)
                return
            self.start_audit(request)

        def start_audit(self, request: _AuditRequest) -> None:
            if not busy.acquire(blocking=False):
                self.send({"error": "已有任務執行中，請等待完成。"}, 409)
                return
            queued = _queued_report(request, uuid.uuid4().hex)
            try:
                store.save(queued)
            except Exception:
                busy.release()
                raise
            threading.Thread(target=self.run_audit, args=(request, queued), daemon=True).start()
            self.send({"id": queued["id"]}, 202)

        def run_audit(self, request: _AuditRequest, queued: JsonObject) -> None:
            try:
                audit(
                    request.target,
                    request.goal,
                    use_ai=request.use_ai,
                    backend=request.backend,
                    emit=store.save,
                    run_id=queued["id"],
                )
            except Exception as exc:
                report = store.get(queued["id"]) or queued
                report["state"] = "failed"
                report["warnings"].append(f"未預期錯誤：{type(exc).__name__}，請查看終端。")
                store.save(report)
                traceback.print_exc()
            finally:
                busy.release()

        def log_message(self, format: str, *args: object) -> None:
            """Keep polling logs quiet; unexpected failures still print tracebacks."""

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
