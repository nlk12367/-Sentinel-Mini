"""Orchestrate planning, tool execution, and independent verification.

The original public imports remain available for callers of version 1.0.
"""

from __future__ import annotations

import copy
import http.client
import json
import subprocess
import sys
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .checks import extract_candidates, validate_plan, verify
from .contracts import ACTIONS, JsonObject, ModelClient, now
from .models import Model, create_model
from .network import Scope

__all__ = ["Model", "Scope", "audit", "extract_candidates", "validate_plan", "verify"]


def tls_command(scope: Scope) -> JsonObject:
    """A fixed argv command, never shell=True and never model-authored code."""
    argv = [
        sys.executable,
        str(Path(__file__).with_name("tls_probe.py")),
        scope.addresses[0],
        str(scope.port),
        scope.host,
    ]
    completed = subprocess.run(
        argv, capture_output=True, text=True, timeout=10, shell=False, encoding="utf-8"
    )
    if completed.returncode:
        raise ValueError("TLS 子程序失敗；請查看 Python 環境。")
    return {
        "id": uuid.uuid4().hex[:12],
        "kind": "tls",
        "time": now(),
        "argv": [Path(sys.executable).name, "tls_probe.py", *argv[2:]],
        "result": json.loads(completed.stdout),
    }


def worker(scope: Scope, action: str) -> JsonObject:
    """Execute one registered action and return evidence-backed observations."""
    if action not in ACTIONS:
        raise ValueError("未登錄的工具 action。")
    if action == "command":
        if scope.scheme != "https":
            return {
                "state": "skipped",
                "note": "HTTP 目標沒有 TLS，略過憑證檢查。",
                "evidence": [],
                "candidates": [],
            }
        evidence = tls_command(scope)
        return {
            "state": "done",
            "note": (
                "TLS 驗證成功。"
                if evidence["result"]["ok"]
                else "TLS 無法確認，詳見執行證據；未直接判定漏洞。"
            ),
            "evidence": [evidence],
            "candidates": [],
        }
    evidence = scope.fetch()
    candidates = extract_candidates(evidence)
    candidates = [c for c in candidates if c["code"].startswith("cookie_") == (action == "request")]
    return {
        "state": "done",
        "note": f'收到 HTTP {evidence["status"]}；產生 {len(candidates)} 項待重測觀察。',
        "evidence": [evidence],
        "candidates": candidates,
    }


@dataclass(frozen=True)
class _AuditOptions:
    use_ai: bool
    backend: str
    run_id: str | None


def _new_report(url: str, goal: str, options: _AuditOptions) -> JsonObject:
    return {
        "id": options.run_id or uuid.uuid4().hex,
        "target": url,
        "goal": goal,
        "mode": "ai" if options.use_ai else "rules",
        "state": "planning",
        "started_at": now(),
        "tasks": [],
        "evidence": [],
        "findings": [],
        "events": [],
        "warnings": [],
        "summary": "",
        "model_calls": 0,
        "backend": options.backend if options.use_ai else None,
    }


class _AuditSession:
    """Own one audit's report and publish independent progress snapshots."""

    def __init__(self, report: JsonObject, emit: Callable[[JsonObject], None] | None) -> None:
        self.report = report
        self.emit = emit
        self.model: ModelClient | None = None

    def event(self, message: str) -> None:
        self.report["events"].append({"time": now(), "message": message})
        if self.emit is not None:
            self.emit(copy.deepcopy(self.report))

    def ask(self, role: str, data: JsonObject) -> JsonObject:
        self.report["model_calls"] += 1
        self.event(f'呼叫 {role} 模型（第 {self.report["model_calls"]} 次，上限 5 次）')
        return self.model.ask(role, data)

    def run(self, use_ai: bool, backend: str) -> None:
        scope = self.prepare_scope()
        self.plan_tasks(scope, use_ai, backend)
        candidates = self.execute_tasks(scope)
        self.verify_results(scope, candidates)
        self.set_completion_state()

    def prepare_scope(self) -> Scope:
        goal = self.report["goal"]
        if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 1000:
            raise ValueError("目標說明須為 1–1000 字。")
        scope = Scope(self.report["target"])
        self.report["target"] = scope.url
        self.report["scope"] = {
            "origin": scope.authority,
            "addresses": scope.addresses,
            "max_http_requests": 3,
            "redirects": False,
        }
        self.event("規劃開始：鎖定單一 origin 與解析 IP。")
        return scope

    def plan_tasks(self, scope: Scope, use_ai: bool, backend: str) -> None:
        if backend not in ("codex", "compatible"):
            raise ValueError("未知的模型 backend。")
        self.model = create_model(backend) if use_ai else None
        if self.model:
            self.report["model"] = self.model.name
            plan = validate_plan(
                self.ask(
                    "planner",
                    {
                        "goal": self.report["goal"],
                        "target": scope.url,
                        "actions": ACTIONS,
                    },
                )
            )
        else:
            plan = [{"action": action, "reason": definition[1]} for action, definition in ACTIONS.items()]
        self.report["tasks"] = [
            {"id": index + 1, **task, "title": ACTIONS[task["action"]][0], "state": "queued", "note": ""}
            for index, task in enumerate(plan)
        ]
        self.report["state"] = "executing"
        self.event(f"規劃完成：{len(plan)} 項任務，最多 3 個工具 Worker 並行。")

    def execute_tasks(self, scope: Scope) -> list[JsonObject]:
        candidates = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}
            for task in self.report["tasks"]:
                task["state"] = "running"
                futures[pool.submit(worker, scope, task["action"])] = task
            self.event("開始執行工具。")
            for future in as_completed(futures):
                candidates.extend(self.complete_task(future, futures[future]))
        return candidates

    def complete_task(self, future: Future[JsonObject], task: JsonObject) -> list[JsonObject]:
        candidates = []
        try:
            result = future.result()
            task["state"], task["note"] = result["state"], result["note"]
            self.report["evidence"].extend(result["evidence"])
            candidates.extend(result["candidates"])
            task["evidence_ids"] = [item["id"] for item in result["evidence"]]
            self.annotate_task(task, result)
        except (OSError, ValueError, http.client.HTTPException, subprocess.SubprocessError) as exc:
            task["state"] = "failed"
            task["note"] = f"工具執行失敗：{type(exc).__name__}"
        self.event(task["title"] + "：" + task["note"])
        return candidates

    def annotate_task(self, task: JsonObject, result: JsonObject) -> None:
        if not self.model or result["state"] == "skipped":
            return
        data = {
            "action": task["action"],
            "observations": result["candidates"],
            "evidence": [
                {key: value for key, value in item.items() if key != "body"} for item in result["evidence"]
            ],
        }
        try:
            task["ai_note"] = self.ask("worker", data)["note"]
        except ValueError as exc:
            self.report["warnings"].append(str(exc))

    def verify_results(self, scope: Scope, candidates: list[JsonObject]) -> None:
        self.report["state"] = "verifying"
        self.event(f"獨立確認開始：重測 {len(candidates)} 項觀察。")
        self.report["findings"], evidence = verify(scope, candidates)
        self.report["evidence"].extend(evidence)
        confirmed = sum(finding["status"] == "confirmed" for finding in self.report["findings"])
        self.report["summary"] = (
            f"確認 {confirmed} 項可重現的設定觀察。這些結果不等於已證明可利用漏洞；未發現也不代表網站安全。"
        )
        if not self.model:
            return
        try:
            self.report["ai_summary"] = self.ask(
                "verifier",
                {
                    "findings": self.report["findings"],
                    "summary": self.report["summary"],
                },
            )["note"]
        except ValueError as exc:
            self.report["warnings"].append(str(exc))

    def set_completion_state(self) -> None:
        has_failures = (
            bool(self.report["warnings"])
            or any(task["state"] == "failed" for task in self.report["tasks"])
            or any(finding["status"] == "inconclusive" for finding in self.report["findings"])
        )
        self.report["state"] = "partial" if has_failures else "completed"


def audit(
    url: str,
    goal: str,
    *,
    use_ai: bool = False,
    backend: str = "codex",
    emit: Callable[[JsonObject], None] | None = None,
    run_id: str | None = None,
) -> JsonObject:
    """Run an audit with the original public arguments and report structure."""
    options = _AuditOptions(use_ai, backend, run_id)
    report = _new_report(url, goal, options)
    session = _AuditSession(report, emit)
    try:
        session.run(use_ai, backend)
    except (OSError, ValueError) as exc:
        report["state"] = "failed"
        report["warnings"].append(str(exc))
        report["summary"] = "流程未完成；請查看事件與錯誤。"
    report["finished_at"] = now()
    session.event("流程結束：" + report["state"])
    return report
