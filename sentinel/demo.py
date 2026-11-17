"""Local fixture with intentionally incomplete configuration; no exploit endpoints."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in ("/", "/fixed"):
            self.send_error(404)
            return
        fixed = self.path == "/fixed"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if fixed:
            self.send_header("Content-Security-Policy", "default-src 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Set-Cookie", "demo_session=fake-value; HttpOnly; Secure; SameSite=Lax; Path=/")
        else:
            self.send_header("Set-Cookie", "demo_session=fake-value; Path=/")
        body = (
            '<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
            "<title>Sentinel 本機測試網站</title><h1>本機測試網站</h1>"
            "<p>這是專案內建的設定檢查 fixture；不提供攻擊功能。</p>"
            "<p>"
            + ("已補齊示範安全標頭與 Cookie 屬性。" if fixed else "刻意缺少 CSP、nosniff 與 Cookie 屬性。")
            + '</p><a href="/fixed">已修正版本</a></html>'
        ).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress routine fixture traffic."""


def make_demo(port: int = 8766) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), DemoHandler)
