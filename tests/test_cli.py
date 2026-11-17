"""CLI report files and exit codes remain stable after entrypoint refactoring."""

import json

import pytest

import app


@pytest.mark.parametrize("state,exit_code", [("completed", 0), ("partial", 1), ("failed", 1)])
def test_cli_writes_both_formats_and_returns_audit_status(tmp_path, monkeypatch, state, exit_code):
    report = {
        "id": "example",
        "target": "http://127.0.0.1/",
        "goal": "test",
        "mode": "rules",
        "state": state,
        "started_at": "2026-11-17T00:00:00+00:00",
        "summary": "result",
        "tasks": [],
        "findings": [],
        "warnings": [],
        "evidence": [],
    }
    monkeypatch.setattr(app, "audit", lambda *args, **kwargs: report)
    output = tmp_path / "reports" / "latest.json"
    args = app.build_parser().parse_args(["--target", report["target"], "--authorized", "--out", str(output)])
    assert app.run_cli(args) == exit_code
    assert json.loads(output.read_text(encoding="utf-8"))["state"] == state
    assert "Sentinel Mini" in output.with_suffix(".md").read_text(encoding="utf-8")
