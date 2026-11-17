import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from sentinel.core import Model, Scope, audit, tls_command, verify
from sentinel.demo import make_demo
from sentinel.store import Store, markdown
from sentinel.web import make_server


@pytest.fixture
def demo():
    server = make_demo(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def fake_model(monkeypatch):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(data)
            role = data["messages"][0]["content"]
            if "1–3" in role:
                content = {
                    "tasks": [
                        {"action": "scan", "reason": "檢查標頭"},
                        {"action": "request", "reason": "檢查 Cookie"},
                    ]
                }
            else:
                content = {"note": "依據實際工具結果整理。"}
            body = json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("SENTINEL_LLM_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setenv("SENTINEL_LLM_MODEL", "fake-test-model")
    monkeypatch.setenv("SENTINEL_LLM_API_KEY", "private-test-key")
    yield calls
    server.shutdown()
    server.server_close()
    thread.join()


def test_ai_contract_with_local_api_fixture(demo, fake_model):
    report = audit(demo, "檢查設定", use_ai=True, backend="compatible")
    assert report["state"] == "completed"
    assert report["model_calls"] == 4
    assert len(fake_model) == 4
    assert report["ai_summary"]
    assert len(report["findings"]) == 5
    assert all(f["status"] == "confirmed" for f in report["findings"])
    assert "fake-value" not in json.dumps(fake_model)
    assert "private-test-key" not in json.dumps(report)


def test_missing_ai_config_fails_without_rule_fallback(demo, monkeypatch):
    monkeypatch.delenv("SENTINEL_LLM_BASE_URL", raising=False)
    report = audit(demo, "檢查設定", use_ai=True, backend="compatible")
    assert report["state"] == "failed"
    assert report["tasks"] == []
    assert report["mode"] == "ai"


def test_fixed_fixture_has_no_configuration_findings(demo):
    report = audit(demo + "fixed", "重測修正設定")
    assert report["state"] == "completed"
    assert report["findings"] == []


def test_failed_retest_never_confirms(demo, monkeypatch):
    scope = Scope(demo)

    def fail():
        raise TimeoutError("test timeout")

    monkeypatch.setattr(scope, "fetch", fail)
    findings, evidence = verify(scope, [{"code": "csp_missing", "cookie": "", "evidence_ids": ["original"]}])
    assert findings[0]["status"] == "inconclusive"
    assert evidence == []


def test_fixed_tls_argv_has_no_shell(demo, monkeypatch):
    class Completed:
        returncode = 0
        stdout = '{"ok": true, "version": "TLSv1.3"}'

    def run(argv, **kwargs):
        assert kwargs["shell"] is False
        assert argv[1].endswith("tls_probe.py")
        assert len(argv) == 5
        return Completed()

    monkeypatch.setattr("sentinel.core.subprocess.run", run)
    assert tls_command(Scope(demo))["result"]["ok"]


def test_sqlite_recovery_and_markdown(demo, tmp_path):
    path = tmp_path / "runs.sqlite3"
    store = Store(path)
    report = audit(demo, "檢查 <script> 設定")
    store.save(report)
    assert store.get(report["id"])["findings"]
    assert "<script>" not in markdown(report)
    report["state"] = "executing"
    store.save(report)
    reopened = Store(path)
    assert reopened.get(report["id"])["state"] == "interrupted"
    assert reopened.get(report["id"])["evidence"]


def test_web_requires_token_and_authorized_scope(demo, tmp_path):
    store = Store(tmp_path / "runs.sqlite3")
    server = make_server(0, store, demo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/config") as res:
            config = json.load(res)
        with urlopen(base) as res:
            assert b"<!doctype html>" in res.read()
            assert "frame-ancestors" in res.headers["Content-Security-Policy"]
        data = json.dumps({"target": demo, "goal": "test", "mode": "rules", "authorized": True}).encode()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/api/runs", data=data))
        assert error.value.code == 403
        headers = {"Content-Type": "application/json", "X-Sentinel-Token": config["token"]}
        bad = json.dumps({"target": demo, "goal": "test", "mode": "rules", "authorized": False}).encode()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/api/runs", data=bad, headers=headers))
        assert error.value.code == 400
        with urlopen(Request(base + "/api/runs", data=data, headers=headers)) as res:
            assert res.status == 202
            run_id = json.load(res)["id"]
        # Wait for observable completion, with a bounded event-driven callback.
        import time

        for _ in range(100):
            report = store.get(run_id)
            if report and report["state"] in ("completed", "failed", "partial"):
                break
            time.sleep(0.02)
        assert report["state"] == "completed"
        with urlopen(base + "/api/runs/" + run_id + "/markdown") as res:
            assert b"Sentinel Mini" in res.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
