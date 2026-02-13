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
    if state in {"pending", "assigned", "accepted", "validated", "blocked", "needs_input"}:
        return state
    return "pending"


def is_dependency_satisfied(dep_state: str) -> bool:
    return dep_state in {"accepted", "validated"}


def is_candidate_state(record: dict[str, Any], max_attempts: int) -> tuple[bool, str | None]:
    state = normalize_state(record.get("state"))
    if state == "pending":
        return (True, None)
    if state == "needs_input":
        attempts = int(record.get("attempts", 0))
        if attempts < max_attempts:
            return (True, None)
        return (False, f"needs_input attempts exhausted ({attempts} >= {max_attempts})")
    return (False, f"state {state} is not eligible")


def evaluate_candidates(
    task_graph: list[dict[str, Any]], task_status: dict[str, Any], max_attempts: int
) -> list[dict[str, Any]]:
    records = task_status.get("tasks", {})
    evaluations: list[dict[str, Any]] = []

    for task in task_graph:
        task_id = task["task_id"]
        record = records.get(task_id, {})
        state = normalize_state(record.get("state"))
        candidate_ok, candidate_reject_reason = is_candidate_state(record, max_attempts)
        deps = task.get("blocking_dependencies", [])
        deps_satisfied = all(
            is_dependency_satisfied(normalize_state(records.get(dep, {}).get("state"))) for dep in deps
        )
        reject_reason = None
        if not candidate_ok:
            reject_reason = candidate_reject_reason
        elif not deps_satisfied:
            reject_reason = "blocking dependencies not satisfied"

        evaluations.append(
            {
                "task": task,
                "state": state,
                "deps": deps,
                "deps_satisfied": deps_satisfied,
                "eligible": candidate_ok and deps_satisfied,
                "reject_reason": reject_reason,
            }
        )

    return evaluations


def select_unblocked_tasks(task_graph: list[dict[str, Any]], task_status: dict[str, Any], max_attempts: int = 2) -> list[dict[str, Any]]:
    evaluations = evaluate_candidates(task_graph, task_status, max_attempts=max_attempts)
    return [entry["task"] for entry in evaluations if entry["eligible"]]


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
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--task", help="Force a specific task ID.")
    parser.add_argument("--explain-selection", action="store_true")
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
        forced = task_map[args.task]
        candidates = [forced]
        evaluations = [
            {
                "task": forced,
                "state": normalize_state(task_status["tasks"][args.task].get("state")),
                "deps": forced.get("blocking_dependencies", []),
                "deps_satisfied": True,
                "eligible": True,
                "reject_reason": None,
            }
        ]
    else:
        evaluations = evaluate_candidates(task_graph, task_status, max_attempts=max(args.max_attempts, 0))
        candidates = [entry["task"] for entry in evaluations if entry["eligible"]]

    ranked = sorted(candidates, key=lambda task: task_score(task, module_phase, downstream_map), reverse=True)
    picked = ranked[: max(args.pick, 0)]

    if args.explain_selection:
        for entry in sorted(evaluations, key=lambda item: item["task"]["task_id"]):
            score = task_score(entry["task"], module_phase, downstream_map)
            print(
                " | ".join(
                    [
                        f"task={entry['task']['task_id']}",
                        f"state={entry['state']}",
                        f"deps={entry['deps']}",
                        f"deps_satisfied={entry['deps_satisfied']}",
                        f"score={score}",
                        f"reject_reason={entry['reject_reason'] or '-'}",
                    ]
                )
            )

        would_pick = [task["task_id"] for task in picked]
        print(f"Would select: {would_pick}")

    if not picked:
        print("No eligible tasks found.")
        return 0

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    decisions: list[dict[str, Any]] = []

    for task in picked:
        task_id = task["task_id"]
        record = task_status["tasks"][task_id]
        previous_state = normalize_state(record.get("state"))
        if previous_state == "pending" and not args.dry_run:
            record["state"] = "assigned"
            record["last_updated"] = timestamp

        resulting_state = record.get("state", previous_state)
        if previous_state == "pending" and args.dry_run:
            resulting_state = "assigned"

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
            "new_state": resulting_state,
            "score": {
                "bootstrap_priority": score[0],
                "mvp_priority": score[1],
                "unlock_count": score[2],
            },
            "dry_run": args.dry_run,
        }
        decisions.append(decision)
        if not args.dry_run:
            append_decision_log(Path(args.decision_log), decision)
        print(f"Selected {task_id} (state {previous_state} -> {resulting_state})")

    if args.dry_run:
        print("Dry run: state files were not modified.")
    else:
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
