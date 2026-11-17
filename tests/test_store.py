"""Regression checks for connection ownership and complete crash recovery."""

import sqlite3

import pytest

from sentinel.store import Store


def report(run_id: str, state: str = "completed") -> dict:
    return {
        "id": run_id,
        "started_at": run_id,
        "target": "http://127.0.0.1/",
        "goal": "test",
        "mode": "rules",
        "state": state,
        "warnings": [],
    }


def test_connections_close_and_failed_transaction_rolls_back(tmp_path, monkeypatch):
    connections = []
    original_connect = sqlite3.connect

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    def connect(*args, **kwargs):
        connection = original_connect(*args, factory=TrackedConnection, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr("sentinel.store.sqlite3.connect", connect)
    store = Store(tmp_path / "runs.sqlite3")
    store.save(report("001"))
    assert store.get("001")["state"] == "completed"
    assert len(store.list()) == 1
    with pytest.raises(RuntimeError, match="rollback"):
        with store.connect() as connection:
            connection.execute("DELETE FROM runs WHERE id=?", ("001",))
            raise RuntimeError("rollback")
    assert store.get("001") is not None
    assert connections and all(connection.closed for connection in connections)


def test_recovery_includes_runs_outside_the_history_window(tmp_path):
    path = tmp_path / "runs.sqlite3"
    store = Store(path)
    store.save(report("000", state="executing"))
    for index in range(1, 102):
        store.save(report(f"{index:03d}"))
    assert len(store.list()) == 100
    assert "000" not in {row["id"] for row in store.list()}
    recovered = Store(path)
    assert recovered.get("000")["state"] == "interrupted"
    assert recovered.get("101")["state"] == "completed"
