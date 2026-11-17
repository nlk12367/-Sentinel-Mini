"""HTTP authorization, job exclusivity, and background error recovery."""

import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from sentinel import web
from sentinel.store import Store


@pytest.fixture
def service(tmp_path):
    store = Store(tmp_path / "runs.sqlite3")
    server = web.make_server(0, store, "http://127.0.0.1/")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    with urlopen(base + "/api/config") as response:
        token = json.load(response)["token"]
    yield base, token, store
    server.shutdown()
    server.server_close()
    thread.join()


def post(service, *, overrides=None, headers=None):
    base, token, _ = service
    data = {"target": "http://127.0.0.1/", "goal": "fixture", "mode": "rules", "authorized": True}
    data.update(overrides or {})
    request_headers = {"Content-Type": "application/json", "X-Sentinel-Token": token}
    request_headers.update(headers or {})
    request = Request(base + "/api/runs", data=json.dumps(data).encode(), headers=request_headers)
    with urlopen(request) as response:
        return json.load(response)


def wait_until_finished(store, run_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        report = store.get(run_id)
        if report["state"] in ("completed", "failed", "partial"):
            return report
        time.sleep(0.01)
    pytest.fail("Background fixture did not finish within three seconds.")


@pytest.mark.parametrize(
    "overrides",
    [
        {"authorized": False},
        {"goal": ""},
        {"goal": "x" * 1001},
        {"mode": "unknown"},
        {"backend": "unknown"},
        {"target": "file:///test"},
    ],
)
def test_invalid_requests_do_not_create_jobs(service, overrides):
    with pytest.raises(HTTPError) as error:
        post(service, overrides=overrides)
    assert error.value.code == 400
    assert service[2].list() == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://untrusted.example"},
        {"Host": "untrusted.example"},
        {"X-Sentinel-Token": "wrong-token"},
    ],
)
def test_unauthorized_requests_do_not_create_jobs(service, headers):
    with pytest.raises(HTTPError) as error:
        post(service, headers=headers)
    assert error.value.code == 403
    assert service[2].list() == []


def test_only_one_job_runs_at_a_time(service, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    store = service[2]

    def audit(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=3)
        report = store.get(kwargs["run_id"])
        report["state"] = "completed"
        kwargs["emit"](report)

    monkeypatch.setattr(web, "audit", audit)
    try:
        run_id = post(service)["id"]
        assert entered.wait(timeout=1)
        with pytest.raises(HTTPError) as error:
            post(service)
        assert error.value.code == 409
    finally:
        release.set()
    assert wait_until_finished(store, run_id)["state"] == "completed"


def test_background_error_releases_job_lock(service, monkeypatch):
    store = service[2]
    calls = []

    def audit(*args, **kwargs):
        calls.append(kwargs["run_id"])
        if len(calls) == 1:
            raise RuntimeError("fixture background failure")
        report = store.get(kwargs["run_id"])
        report["state"] = "completed"
        kwargs["emit"](report)

    monkeypatch.setattr(web, "audit", audit)
    first = wait_until_finished(store, post(service)["id"])
    assert first["state"] == "failed"
    assert "RuntimeError" in first["warnings"][0]
    second = wait_until_finished(store, post(service)["id"])
    assert second["state"] == "completed"
