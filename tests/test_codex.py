import json
import subprocess
from pathlib import Path

import pytest

from sentinel.codex_model import CodexModel


def test_codex_uses_stdin_schema_and_readonly(monkeypatch, tmp_path):
    monkeypatch.setattr("sentinel.codex_model.find_codex", lambda: ["codex.exe"])
    model = CodexModel()
    model.calls_dir = tmp_path

    def run(argv, **kwargs):
        assert argv[argv.index("--sandbox") + 1] == "read-only"
        assert "--ignore-user-config" in argv and "--ephemeral" in argv
        assert kwargs["shell"] is False
        assert "untrusted-value" in kwargs["input"]
        assert "untrusted-value" not in " ".join(argv)
        schema = json.loads(Path(argv[argv.index("--output-schema") + 1]).read_text())
        assert schema["additionalProperties"] is False
        Path(argv[argv.index("--output-last-message") + 1]).write_text('{"note":"ok"}', encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr("sentinel.codex_model.subprocess.run", run)
    assert model.ask("worker", {"value": "untrusted-value"}) == {"note": "ok"}
    assert list(tmp_path.iterdir()) == []


def test_codex_failure_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr("sentinel.codex_model.find_codex", lambda: ["codex.exe"])
    model = CodexModel()
    model.calls_dir = tmp_path
    monkeypatch.setattr(
        "sentinel.codex_model.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 1)
    )
    with pytest.raises(ValueError, match="exit 1"):
        model.ask("planner", {})
