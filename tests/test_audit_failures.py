"""Characterize failure boundaries before changing audit orchestration."""

import pytest

from sentinel import core


class MemoryScope:
    url = "http://fixture.test:80/"
    authority = "fixture.test:80"
    addresses = ["127.0.0.1"]
    scheme = "http"

    def __init__(self, url):
        self.requests = 0

    def fetch(self):
        self.requests += 1
        return {
            "id": f"http-{self.requests}",
            "status": 200,
            "body": "fixture-body",
            "headers": [("Content-Type", "text/html"), ("Set-Cookie", "session=[REDACTED]; Path=/")],
        }


class FakeModel:
    name = "fixture-model"

    def __init__(self, failure):
        self.failure = failure

    def ask(self, role, data):
        if role == self.failure:
            raise ValueError(f"{role} unavailable")
        if role == "planner":
            return {
                "tasks": [{"action": "scan", "reason": "headers"}, {"action": "request", "reason": "cookies"}]
            }
        assert "fixture-body" not in str(data)
        return {"note": "fixture-note"}


@pytest.mark.parametrize(
    "failure,state,calls", [("planner", "failed", 1), ("worker", "partial", 4), ("verifier", "partial", 4)]
)
def test_model_failure_preserves_role_boundaries(monkeypatch, failure, state, calls):
    monkeypatch.setattr(core, "Scope", MemoryScope)
    monkeypatch.setattr(core, "create_model", lambda backend: FakeModel(failure))
    snapshots = []
    report = core.audit("http://fixture.test/", "test", use_ai=True, emit=snapshots.append)
    assert report["state"] == state
    assert report["model_calls"] == calls
    assert report["warnings"] and failure in report["warnings"][0]
    assert snapshots[-1] == report
    assert snapshots[0]["state"] == "planning"
    if failure == "planner":
        assert report["tasks"] == [] and report["evidence"] == []
    else:
        assert all(task["state"] == "done" for task in report["tasks"])
        assert len(report["findings"]) == 5
        assert all(finding["status"] == "confirmed" for finding in report["findings"])
        assert bool(report.get("ai_summary")) == (failure != "verifier")


def test_one_tool_failure_keeps_other_evidence(monkeypatch):
    monkeypatch.setattr(core, "Scope", MemoryScope)
    original = core.worker

    def worker(scope, action):
        if action == "scan":
            raise OSError("fixture failure")
        return original(scope, action)

    monkeypatch.setattr(core, "worker", worker)
    report = core.audit("http://fixture.test/", "test")
    assert report["state"] == "partial"
    assert [task["state"] for task in report["tasks"]] == ["failed", "skipped", "done"]
    assert len(report["findings"]) == 3
    assert len(report["evidence"]) == 2
    assert all(finding["status"] == "confirmed" for finding in report["findings"])
