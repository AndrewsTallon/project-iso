#!/usr/bin/env python3
"""Generate deterministic control/module/BSI coverage state."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUS_ORDER = ["unknown", "planned", "in_progress", "accepted", "validated"]
STATUS_RANK = {name: idx for idx, name in enumerate(STATUS_ORDER)}
CONFIDENCE_BY_STATUS = {
    "unknown": 0.0,
    "planned": 0.3,
    "in_progress": 0.3,
    "accepted": 0.6,
    "validated": 0.9,
}
OUTPUT_STATUS_MAP = {
    "ok": "accepted",
    "needs_input": "in_progress",
    "blocked": "planned",
    "error": "planned",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def max_status(a: str, b: str) -> str:
    return a if STATUS_RANK[a] >= STATUS_RANK[b] else b


def status_from_tasks(task_states: list[str]) -> str:
    status = "unknown"
    for task_state in task_states:
        status = max_status(status, task_state)
    return status


def normalize_task_state(raw: str | None) -> str:
    if raw in STATUS_RANK:
        return raw
    mapping = {
        "pending": "planned",
        "assigned": "in_progress",
        "accepted": "accepted",
        "validated": "validated",
        "blocked": "planned",
    }
    if raw in mapping:
        return mapping[raw]
    return "unknown"


def collect_task_status(task_id: str, task_status: dict[str, Any], output_payloads: dict[str, dict[str, Any]]) -> str:
    record = task_status.get(task_id, {})
    file_state = normalize_task_state(record.get("state"))

    output_state = "unknown"
    output_payload = output_payloads.get(task_id)
    if output_payload is not None:
        output_state = OUTPUT_STATUS_MAP.get(output_payload.get("status"), "accepted")

    return max_status(file_state, output_state)


def load_outputs(work_outputs_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for path in sorted(work_outputs_dir.glob("*.output.json")):
        payload = load_json(path)
        task_id = payload.get("task_id") or path.name.replace(".output.json", "")
        if not isinstance(task_id, str) or not task_id:
            continue
        payloads[task_id] = payload
    return payloads


def build_coverage(plan: dict[str, Any], controls: list[dict[str, Any]], task_status: dict[str, Any], output_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    modules = {
        module["module_id"]: module
        for module in plan["architecture_summary"].get("core_modules", [])
        if "module_id" in module
    }

    module_phase: dict[str, str] = {}
    for phase in plan.get("implementation_phases", []):
        for module_id in phase.get("focus_modules", []):
            module_phase[module_id] = phase.get("phase", "")

    task_graph = plan.get("task_graph", [])
    tasks_by_control: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tasks_by_module: dict[str, list[dict[str, Any]]] = defaultdict(list)
    downstream: dict[str, list[str]] = defaultdict(list)
    for task in task_graph:
        for control in task.get("control_scope", []):
            tasks_by_control[control].append(task)
        tasks_by_module[task.get("module_id", "")].append(task)
        for dep in task.get("blocking_dependencies", []):
            downstream[dep].append(task["task_id"])

    module_controls: dict[str, set[str]] = defaultdict(set)
    for module_id, module in modules.items():
        for control_id in module.get("covers_controls", []):
            module_controls[module_id].add(control_id)

    controls_map: dict[str, dict[str, Any]] = {}
    for row in controls:
        control_id = str(row.get("control_id") or "").strip()
        if control_id:
            controls_map[control_id] = row

    for module in modules.values():
        for control_id in module.get("covers_controls", []):
            controls_map.setdefault(control_id, {"control_id": control_id})

    task_states: dict[str, str] = {}
    for task in task_graph:
        task_states[task["task_id"]] = collect_task_status(task["task_id"], task_status, output_payloads)

    validated_controls: set[str] = set()
    for task_id, payload in output_payloads.items():
        if payload.get("status") != "ok" or payload.get("assigned_agent") != "qa_validation":
            continue
        task = next((item for item in task_graph if item["task_id"] == task_id), None)
        if task:
            validated_controls.update(task.get("control_scope", []))

    by_control: dict[str, Any] = {}
    for control_id in sorted(controls_map):
        row = controls_map[control_id]
        control_tasks = tasks_by_control.get(control_id, [])
        task_ids = sorted(task["task_id"] for task in control_tasks)
        task_statuses = [task_states[task_id] for task_id in task_ids]

        status = status_from_tasks(task_statuses)
        if control_id in validated_controls:
            status = "validated"

        modules_for_control = sorted(
            module_id
            for module_id, module in modules.items()
            if control_id in module.get("covers_controls", [])
        )

        artifacts: list[str] = []
        for task_id in task_ids:
            payload = output_payloads.get(task_id)
            if not payload:
                continue
            for produced_file in payload.get("produced_files", []):
                if isinstance(produced_file, str):
                    artifacts.append(produced_file)
            artifacts.append(f"work_outputs/{task_id}.output.json")

        by_control[control_id] = {
            "automation_level": str(row.get("automation_potential") or ""),
            "complexity": str(row.get("complexity") or ""),
            "confidence": CONFIDENCE_BY_STATUS[status],
            "evidence_artifacts": sorted(set(artifacts)),
            "modules": modules_for_control,
            "status": status,
            "tasks": task_ids,
        }

    by_module: dict[str, Any] = {}
    for module_id in sorted(modules):
        module = modules[module_id]
        controls_for_module = sorted(module_controls[module_id])
        statuses = [by_control[control_id]["status"] for control_id in controls_for_module if control_id in by_control]
        module_status = status_from_tasks(statuses)

        blocking_tasks: list[str] = []
        for task in tasks_by_module.get(module_id, []):
            if task_states.get(task["task_id"]) in {"accepted", "validated"}:
                continue
            deps = task.get("blocking_dependencies", [])
            unmet = [dep for dep in deps if task_states.get(dep) not in {"accepted", "validated"}]
            if unmet:
                blocking_tasks.append(task["task_id"])

        controls_validated = sum(1 for control_id in controls_for_module if by_control.get(control_id, {}).get("status") == "validated")
        by_module[module_id] = {
            "blocking_tasks": sorted(set(blocking_tasks)),
            "bsi_domains": sorted(module.get("bsi_domains", [])),
            "controls_total": len(controls_for_module),
            "controls_validated": controls_validated,
            "phase": module_phase.get(module_id, ""),
            "status": module_status,
        }

    by_bsi_domain: dict[str, Any] = {}
    domain_modules: dict[str, set[str]] = defaultdict(set)
    domain_controls: dict[str, set[str]] = defaultdict(set)
    for module_id, module in modules.items():
        controls_for_module = set(module.get("covers_controls", []))
        for domain in module.get("bsi_domains", []):
            domain_modules[domain].add(module_id)
            domain_controls[domain].update(controls_for_module)

    for domain in sorted(domain_modules):
        controls_for_domain = sorted(domain_controls[domain])
        statuses = [by_control[control_id]["status"] for control_id in controls_for_domain if control_id in by_control]
        by_bsi_domain[domain] = {
            "controls": controls_for_domain,
            "modules": sorted(domain_modules[domain]),
            "status": status_from_tasks(statuses),
        }

    control_status_counter = Counter(item["status"] for item in by_control.values())

    top_modules_blocked = sorted(
        (
            {
                "module_id": module_id,
                "blocking_tasks": data["blocking_tasks"],
                "blocking_count": len(data["blocking_tasks"]),
            }
            for module_id, data in by_module.items()
            if data["blocking_tasks"]
        ),
        key=lambda item: (-item["blocking_count"], item["module_id"]),
    )[:5]

    top_iso_controls_missing = sorted(
        (
            {
                "control_id": control_id,
                "status": data["status"],
                "task_count": len(data["tasks"]),
            }
            for control_id, data in by_control.items()
            if data["status"] not in {"accepted", "validated"}
        ),
        key=lambda item: (STATUS_RANK[item["status"]], -item["task_count"], item["control_id"]),
    )[:10]

    top_bsi_domains_missing = sorted(
        (
            {
                "domain": domain,
                "status": data["status"],
                "controls_count": len(data["controls"]),
            }
            for domain, data in by_bsi_domain.items()
            if data["status"] not in {"accepted", "validated"}
        ),
        key=lambda item: (STATUS_RANK[item["status"]], -item["controls_count"], item["domain"]),
    )[:5]

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "by_control": by_control,
        "by_module": by_module,
        "by_bsi_domain": by_bsi_domain,
        "overall": {
            "controls_total": len(by_control),
            "controls_with_tasks": sum(1 for data in by_control.values() if data["tasks"]),
            "controls_unknown": control_status_counter.get("unknown", 0),
            "controls_planned": control_status_counter.get("planned", 0),
            "controls_in_progress": control_status_counter.get("in_progress", 0),
            "controls_accepted": control_status_counter.get("accepted", 0),
            "controls_validated": control_status_counter.get("validated", 0),
            "modules_total": len(by_module),
            "modules_validated": sum(1 for data in by_module.values() if data["status"] == "validated"),
            "bsi_domains_total": len(by_bsi_domain),
            "bsi_domains_validated": sum(1 for data in by_bsi_domain.values() if data["status"] == "validated"),
            "work_outputs_total": len(output_payloads),
        },
        "gaps": {
            "top_modules_blocked": top_modules_blocked,
            "top_iso_controls_missing": top_iso_controls_missing,
            "top_bsi_domains_missing": top_bsi_domains_missing,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic coverage summaries.")
    parser.add_argument("--plan", default="architecture_plan.json")
    parser.add_argument("--controls", default="data/controls.json")
    parser.add_argument("--work-outputs", default="work_outputs")
    parser.add_argument("--task-status", default="state/task_status.json")
    parser.add_argument("--output", default="state/coverage.json")
    args = parser.parse_args()

    plan = load_json(Path(args.plan))
    controls = load_json(Path(args.controls))

    task_status = {}
    task_status_path = Path(args.task_status)
    if task_status_path.exists():
        payload = load_json(task_status_path)
        task_status = payload.get("tasks", {}) if isinstance(payload, dict) else {}

    output_payloads = load_outputs(Path(args.work_outputs)) if Path(args.work_outputs).exists() else {}

    coverage = build_coverage(plan, controls, task_status, output_payloads)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(stable_dump(coverage), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
