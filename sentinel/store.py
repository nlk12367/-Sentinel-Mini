"""SQLite snapshots: every event is one atomic transaction."""

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .contracts import JsonObject
from .reporting import markdown  # Preserve the original public import.

__all__ = ["Store", "markdown"]


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.Lock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, started TEXT, body TEXT)")
        self._recover_interrupted()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Commit or roll back a transaction, then always close its connection."""
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _recover_interrupted(self) -> None:
        """Recover all unfinished runs, independent of the UI history limit."""
        active_states = {"queued", "planning", "executing", "verifying"}
        with self.connect() as db:
            rows = db.execute("SELECT id, body FROM runs").fetchall()
            for run_id, body in rows:
                report = json.loads(body)
                if report["state"] not in active_states:
                    continue
                report["state"] = "interrupted"
                report["warnings"].append("上次程序中止；保留已完成證據，請建立新任務重新檢查。")
                db.execute(
                    "UPDATE runs SET body=? WHERE id=?", (json.dumps(report, ensure_ascii=False), run_id)
                )

    def save(self, report: JsonObject) -> None:
        body = json.dumps(report, ensure_ascii=False)
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO runs VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                (report["id"], report["started_at"], body),
            )

    def get(self, run_id: str) -> JsonObject | None:
        with self.connect() as db:
            row = db.execute("SELECT body FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self) -> list[JsonObject]:
        with self.connect() as db:
            rows = db.execute("SELECT body FROM runs ORDER BY started DESC LIMIT 100").fetchall()
        fields = ("id", "target", "goal", "state", "started_at", "mode")
        reports = (json.loads(row[0]) for row in rows)
        return [{key: report[key] for key in fields} for report in reports]
