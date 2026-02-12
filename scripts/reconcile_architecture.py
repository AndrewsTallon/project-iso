#!/usr/bin/env python3
"""Conservative architecture reconciler based on accepted machine outputs only."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACCEPTED_STATES = {"accepted", "validated"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_task_filter(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def get_allowed_tasks(task_status: dict[str, Any], task_filter: set[str] | None) -> set[str]:
    records = task_status.get("tasks", {})
    allowed: set[str] = set()
    if isinstance(records, dict):
        for task_id, payload in records.items():
            if not isinstance(payload, dict):
                continue
            if payload.get("state") in ACCEPTED_STATES:
                if task_filter is None or task_id in task_filter:
                    allowed.add(task_id)
    return allowed


def discover_outputs(work_outputs_dir: Path, allowed_tasks: set[str]) -> list[tuple[str, Path, dict[str, Any]]]:
    outputs: list[tuple[str, Path, dict[str, Any]]] = []
    if not work_outputs_dir.exists():
        return outputs

    for candidate in sorted(work_outputs_dir.glob("*.output.json")):
        try:
            payload = load_json(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        task_id = payload.get("task_id")
        if not isinstance(task_id, str):
            continue
        if task_id not in allowed_tasks:
            continue
        outputs.append((task_id, candidate, payload))

    outputs.sort(key=lambda item: (item[0], str(item[1])))
    return outputs


def ensure_top_level_dict(plan: dict[str, Any], field: str) -> dict[str, Any]:
    current = plan.get(field)
    if not isinstance(current, dict):
        current = {}
        plan[field] = current
    return current


def add_change(changes: list[dict[str, Any]], change_type: str, path: str, before: Any, after: Any) -> None:
    changes.append({
        "type": change_type,
        "path": path,
        "before": before,
        "after": after,
    })


def merge_dict_additive(target: dict[str, Any], incoming: dict[str, Any], path_prefix: str, changes: list[dict[str, Any]]) -> None:
    for key in sorted(incoming):
        in_value = incoming[key]
        next_path = f"{path_prefix}.{key}"
        if key not in target:
            target[key] = copy.deepcopy(in_value)
            add_change(changes, "add_field", next_path, None, target[key])
            continue

        cur_value = target[key]
        if isinstance(cur_value, dict) and isinstance(in_value, dict):
            merge_dict_additive(cur_value, in_value, next_path, changes)
            continue

        if isinstance(cur_value, list) and isinstance(in_value, list):
            existing = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in cur_value}
            for item in in_value:
                canonical = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if canonical in existing:
                    continue
                cur_value.append(copy.deepcopy(item))
                existing.add(canonical)
                add_change(changes, "append_list_item", next_path, None, item)
            continue

        # Conservative: never overwrite existing scalar/non-matching structures.


def apply_dependency_updates(
    new_plan: dict[str, Any],
    updates: dict[str, Any],
    all_task_ids: set[str],
    changes: list[dict[str, Any]],
) -> None:
    graph = new_plan.get("task_graph", [])
    if not isinstance(graph, list):
        return

    task_map: dict[str, dict[str, Any]] = {}
    for task in graph:
        if isinstance(task, dict) and isinstance(task.get("task_id"), str):
            task_map[task["task_id"]] = task

    dep_updates = updates.get("dependency_edges")
    if not isinstance(dep_updates, list):
        return

    for dep_update in dep_updates:
        if not isinstance(dep_update, dict):
            continue
        task_id = dep_update.get("task_id")
        depends_on = dep_update.get("depends_on")
        if not isinstance(task_id, str) or not isinstance(depends_on, str):
            continue
        if task_id not in task_map or depends_on not in all_task_ids:
            continue

        task = task_map[task_id]
        deps = task.get("blocking_dependencies")
        if not isinstance(deps, list):
            deps = []
            task["blocking_dependencies"] = deps

        if depends_on in deps:
            continue

        before = list(deps)
        deps.append(depends_on)
        add_change(
            changes,
            "add_dependency",
            f"task_graph.{task_id}.blocking_dependencies",
            before,
            list(deps),
        )


def apply_module_interface_updates(new_plan: dict[str, Any], updates: dict[str, Any], changes: list[dict[str, Any]]) -> None:
    summary = new_plan.get("architecture_summary", {})
    modules = summary.get("core_modules") if isinstance(summary, dict) else None
    if not isinstance(modules, list):
        return

    module_map: dict[str, dict[str, Any]] = {}
    for module in modules:
        if isinstance(module, dict) and isinstance(module.get("module_id"), str):
            module_map[module["module_id"]] = module

    interface_updates = updates.get("module_interfaces")
    if not isinstance(interface_updates, list):
        return

    for entry in interface_updates:
        if not isinstance(entry, dict):
            continue
        module_id = entry.get("module_id")
        interfaces = entry.get("interfaces")
        if not isinstance(module_id, str) or not isinstance(interfaces, list):
            continue
        if module_id not in module_map:
            continue

        target_module = module_map[module_id]
        existing = target_module.get("module_interfaces")
        if not isinstance(existing, list):
            existing = []
            target_module["module_interfaces"] = existing

        existing_names = {
            item.get("name")
            for item in existing
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }

        for iface in interfaces:
            if not isinstance(iface, dict):
                continue
            name = iface.get("name")
            if not isinstance(name, str) or name in existing_names:
                continue
            existing.append(copy.deepcopy(iface))
            existing_names.add(name)
            add_change(
                changes,
                "add_module_interface",
                f"architecture_summary.core_modules.{module_id}.module_interfaces[{name}]",
                None,
                iface,
            )


def apply_architecture_updates(
    new_plan: dict[str, Any],
    architecture_updates: dict[str, Any],
    all_task_ids: set[str],
    changes: list[dict[str, Any]],
) -> None:
    apply_dependency_updates(new_plan, architecture_updates, all_task_ids, changes)
    apply_module_interface_updates(new_plan, architecture_updates, changes)

    constraints_updates = architecture_updates.get("constraints")
    if isinstance(constraints_updates, dict):
        constraints_target = ensure_top_level_dict(new_plan, "constraints")
        merge_dict_additive(constraints_target, constraints_updates, "constraints", changes)

    coverage_updates = architecture_updates.get("coverage_mapping")
    if isinstance(coverage_updates, dict):
        coverage_target = ensure_top_level_dict(new_plan, "coverage_mapping")
        merge_dict_additive(coverage_target, coverage_updates, "coverage_mapping", changes)


def append_decision_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def write_proposal_outputs(
    out_dir: Path,
    timestamp: str,
    plan: dict[str, Any],
    diff: dict[str, Any],
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    next_path = out_dir / f"{timestamp}_architecture_plan.next.json"
    diff_path = out_dir / f"{timestamp}_architecture_plan.diff.json"
    next_path.write_text(stable_dump(plan), encoding="utf-8")
    diff_path.write_text(stable_dump(diff), encoding="utf-8")
    return next_path, diff_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Conservative architecture reconciliation.")
    parser.add_argument("--mode", choices=["propose", "apply"], default="propose")
    parser.add_argument("--task-ids", help="Optional comma-separated task IDs to include.")
    parser.add_argument("--work-outputs", default="work_outputs/")
    parser.add_argument("--architecture", default="architecture_plan.json")
    parser.add_argument("--task-status", default="state/task_status.json")
    parser.add_argument("--out-dir", default="architecture/proposals/")
    parser.add_argument("--decision-log", default="state/decision_log.jsonl")
    args = parser.parse_args()

    architecture_path = Path(args.architecture)
    task_status_path = Path(args.task_status)
    work_outputs_dir = Path(args.work_outputs)

    plan = load_json(architecture_path)
    if not isinstance(plan, dict):
        print("Architecture plan must be a JSON object.", file=sys.stderr)
        return 1

    task_graph = plan.get("task_graph", [])
    all_task_ids = {
        task.get("task_id")
        for task in task_graph
        if isinstance(task, dict) and isinstance(task.get("task_id"), str)
    }

    task_status = load_json(task_status_path)
    if not isinstance(task_status, dict):
        task_status = {"tasks": {}}

    task_filter = parse_task_filter(args.task_ids)
    allowed_tasks = get_allowed_tasks(task_status, task_filter)
    selected_outputs = discover_outputs(work_outputs_dir, allowed_tasks)

    proposed_plan = copy.deepcopy(plan)
    changes: list[dict[str, Any]] = []
    sources: list[str] = []

    for task_id, _path, payload in selected_outputs:
        architecture_updates = payload.get("architecture_updates")
        if not isinstance(architecture_updates, dict):
            continue
        if task_id not in sources:
            sources.append(task_id)
        apply_architecture_updates(proposed_plan, architecture_updates, all_task_ids, changes)

    changes.sort(key=lambda item: (item["type"], item["path"], json.dumps(item.get("after"), sort_keys=True, ensure_ascii=False)))

    timestamp = utc_timestamp()
    diff_payload = {
        "proposed_at": timestamp,
        "sources": sorted(sources),
        "changes": changes,
    }

    proposal_path, diff_path = write_proposal_outputs(Path(args.out_dir), timestamp, proposed_plan, diff_payload)

    archived_path: Path | None = None
    applied = False
    if args.mode == "apply" and changes:
        versions_dir = Path("architecture") / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        archived_path = versions_dir / f"{timestamp}_architecture_plan.json"
        archived_path.write_text(stable_dump(plan), encoding="utf-8")
        architecture_path.write_text(stable_dump(proposed_plan), encoding="utf-8")
        applied = True

    append_decision_log(
        Path(args.decision_log),
        {
            "event": "architecture_reconciled",
            "timestamp": timestamp,
            "mode": args.mode,
            "sources": sorted(sources),
            "changes_count": len(changes),
            "proposal_path": str(proposal_path),
            "diff_path": str(diff_path),
            "applied": applied,
            "archive_path": str(archived_path) if archived_path else "",
        },
    )

    print(f"mode={args.mode} sources={len(sources)} changes={len(changes)}")
    print(f"proposal={proposal_path}")
    print(f"diff={diff_path}")
    if archived_path:
        print(f"archived={archived_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
