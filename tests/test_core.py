import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sentinel.core import Scope, audit, extract_candidates, validate_plan, verify


def test_worker_rejects_unregistered_actions_before_network_access():
    from sentinel.core import worker

    with pytest.raises(ValueError, match="action"):
        worker(None, "shell")


@pytest.fixture
def target():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "http://example.com/")
                self.end_headers()
                return
            self.send_response(200)
            if self.path == "/secure":
                self.send_header("Content-Security-Policy", "default-src 'self'")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Set-Cookie", "session=abc; HttpOnly; Secure; SameSite=Lax")
            else:
                self.send_header("Set-Cookie", "session=abc; Path=/")
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'<form><input type="password"></form>')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "http://example.com/#x",
        "http://example.com:bad",
        "http://example.com/a?token=secret",
        "http://example.com\\@evil.com",
    ],
)
def test_reject_invalid_scope(url):
    with pytest.raises(ValueError):
        Scope(url)


def test_scope_blocks_other_origin(target):
    scope = Scope(target)
    with pytest.raises(ValueError):
        scope.check("http://example.com/")


def test_redirect_is_not_followed(target):
    scope = Scope(target + "/redirect")
    evidence = scope.fetch()
    assert evidence["status"] == 302
    assert evidence["url"].endswith("/redirect")
    assert extract_candidates(evidence) == []


def test_security_findings_require_matching_retest(target):
    scope = Scope(target)
    first = scope.fetch()
    candidates = extract_candidates(first)
    assert "cookie_httponly" in {c["code"] for c in candidates}
    reports, evidence = verify(scope, candidates)
    assert reports and all(r["status"] == "confirmed" for r in reports)
    assert len(evidence) == 1
    changed = Scope(target + "/secure")
    reports, _ = verify(changed, [c for c in candidates if c["code"] == "csp_missing"])
    assert reports[0]["status"] == "not_reproduced"


def test_no_finding_from_error_or_non_html():
    assert extract_candidates({"status": 503, "headers": [], "body": ""}) == []
    assert (
        extract_candidates({"status": 200, "headers": [("Content-Type", "application/json")], "body": "{}"})
        == []
    )


def test_model_plan_cannot_inject_commands():
    with pytest.raises(ValueError):
        validate_plan({"tasks": [{"action": "shell", "reason": "rm"}]})
    with pytest.raises(ValueError):
        validate_plan({"tasks": [{"action": "scan", "reason": "ok"}, {"action": "scan", "reason": "again"}]})


def test_end_to_end_report(target):
    events = []
    report = audit(target, "檢查網站設定", emit=lambda data: events.append(data))
    assert report["state"] == "completed"
    assert len(report["tasks"]) == 3
    assert len(report["evidence"]) == 3  # scan, request, independent retest (TLS skipped for HTTP)
    assert any(f["status"] == "confirmed" for f in report["findings"])
    assert report["tasks"][1]["state"] == "skipped"
    assert "abc" not in json.dumps(report, ensure_ascii=False)
    assert events[-1]["state"] == "completed"
