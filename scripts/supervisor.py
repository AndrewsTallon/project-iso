#!/usr/bin/env python3
"""Select next unblocked tasks and prepare work items deterministically."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PREFERRED_TASKS = {"T01_platform_blueprint", "T02_evidence_chain_design", "T03_shared_connector_framework"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def load_task_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "tasks": {}}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {"schema_version": 1, "tasks": {}}
    payload.setdefault("schema_version", 1)
    payload.setdefault("tasks", {})
    return payload


def infer_module_phase(plan: dict[str, Any]) -> dict[str, str]:
    module_phase: dict[str, str] = {}
    for phase in plan.get("implementation_phases", []):
        for module_id in phase.get("focus_modules", []):
            module_phase[module_id] = phase.get("phase", "")
    return module_phase


def build_downstream_map(task_graph: list[dict[str, Any]]) -> dict[str, set[str]]:
    edges: dict[str, list[str]] = defaultdict(list)
    for task in task_graph:
        for dep in task.get("blocking_dependencies", []):
            edges[dep].append(task["task_id"])

    descendants: dict[str, set[str]] = {}
    for task in task_graph:
        origin = task["task_id"]
        visited: set[str] = set()
        queue = deque(edges.get(origin, []))
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            queue.extend(edges.get(current, []))
        descendants[origin] = visited
    return descendants


def normalize_state(state: str | None) -> str:
    if state in {"pending", "assigned", "accepted", "validated", "blocked"}:
        return state
    return "pending"


def is_dependency_satisfied(dep_state: str) -> bool:
    return dep_state in {"accepted", "validated"}


def select_unblocked_tasks(task_graph: list[dict[str, Any]], task_status: dict[str, Any]) -> list[dict[str, Any]]:
    records = task_status.get("tasks", {})
    selected: list[dict[str, Any]] = []

    for task in task_graph:
        task_id = task["task_id"]
        state = normalize_state(records.get(task_id, {}).get("state"))
        if state in {"accepted", "validated", "assigned"}:
            continue
        deps = task.get("blocking_dependencies", [])
        if all(is_dependency_satisfied(normalize_state(records.get(dep, {}).get("state"))) for dep in deps):
            selected.append(task)
    return selected


def task_score(task: dict[str, Any], module_phase: dict[str, str], downstream_map: dict[str, set[str]]) -> tuple[int, int, int, str]:
    module_id = task.get("module_id", "")
    phase = module_phase.get(module_id, "")
    mvp_priority = 1 if phase == "MVP" else 0
    unlock_count = len(downstream_map.get(task["task_id"], set()))
    bootstrap_priority = 1 if task["task_id"] in PREFERRED_TASKS else 0
    return (bootstrap_priority, mvp_priority, unlock_count, task["task_id"])


def ensure_task_records(task_status: dict[str, Any], task_graph: list[dict[str, Any]]) -> None:
    records = task_status.setdefault("tasks", {})
    for task in task_graph:
        task_id = task["task_id"]
        record = records.setdefault(task_id, {})
        record.setdefault("module_id", task.get("module_id", ""))
        record.setdefault("state", "pending")
        record.setdefault("last_updated", "")


def run_agent_runner(task_id: str, dry_run: bool) -> int:
    cmd = [sys.executable, "scripts/agent_runner.py", "--task-id", task_id]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def append_run_history(path: Path, record: dict[str, Any]) -> None:
    payload = {"schema_version": 1, "runs": []}
    if path.exists():
        loaded = load_json(path)
        if isinstance(loaded, dict):
            payload = loaded
            payload.setdefault("schema_version", 1)
            payload.setdefault("runs", [])

    payload["runs"].append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_dump(payload), encoding="utf-8")


def append_decision_log(path: Path, decision: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic supervisor for task assignment.")
    parser.add_argument("--plan", default="architecture_plan.json")
    parser.add_argument("--task-status", default="state/task_status.json")
    parser.add_argument("--run-history", default="state/run_history.json")
    parser.add_argument("--decision-log", default="state/decision_log.jsonl")
    parser.add_argument("--pick", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--task", help="Force a specific task ID.")
    parser.add_argument("--update-coverage", action="store_true")
    args = parser.parse_args()

    plan = load_json(Path(args.plan))
    task_graph = plan.get("task_graph", [])
    module_phase = infer_module_phase(plan)

    task_status_path = Path(args.task_status)
    task_status = load_task_status(task_status_path)
    ensure_task_records(task_status, task_graph)

    task_map = {task["task_id"]: task for task in task_graph}
    downstream_map = build_downstream_map(task_graph)

    if args.task:
        if args.task not in task_map:
            print(f"Requested task not found: {args.task}")
            return 1
        candidates = [task_map[args.task]]
    else:
        candidates = select_unblocked_tasks(task_graph, task_status)

    ranked = sorted(candidates, key=lambda task: task_score(task, module_phase, downstream_map), reverse=True)
    picked = ranked[: max(args.pick, 0)]

    if not picked:
        print("No eligible tasks found.")
        return 0

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    decisions: list[dict[str, Any]] = []

    for task in picked:
        task_id = task["task_id"]
        record = task_status["tasks"][task_id]
        previous_state = normalize_state(record.get("state"))
        if previous_state == "pending":
            record["state"] = "assigned"
            record["last_updated"] = timestamp

        rc = run_agent_runner(task_id, dry_run=args.dry_run)
        if rc != 0:
            print(f"agent_runner failed for {task_id}")
            return rc

        score = task_score(task, module_phase, downstream_map)
        decision = {
            "event": "task_selected",
            "timestamp": timestamp,
            "task_id": task_id,
            "previous_state": previous_state,
            "new_state": record.get("state", previous_state),
            "score": {
                "bootstrap_priority": score[0],
                "mvp_priority": score[1],
                "unlock_count": score[2],
            },
            "dry_run": args.dry_run,
        }
        decisions.append(decision)
        append_decision_log(Path(args.decision_log), decision)
        print(f"Selected {task_id} (state {previous_state} -> {record.get('state')})")

    task_status_path.parent.mkdir(parents=True, exist_ok=True)
    task_status_path.write_text(stable_dump(task_status), encoding="utf-8")

    append_run_history(
        Path(args.run_history),
        {
            "timestamp": timestamp,
            "dry_run": args.dry_run,
            "picked_tasks": [task["task_id"] for task in picked],
            "pick_count": len(picked),
        },
    )

    if args.update_coverage:
        rc = subprocess.run([sys.executable, "scripts/generate_coverage.py"], check=False).returncode
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
