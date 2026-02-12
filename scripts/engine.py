#!/usr/bin/env python3
"""Autonomous loop runner for the project ISO self-expanding cycle."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

import importlib.util


def load_supervisor_module() -> Any:
    spec = importlib.util.spec_from_file_location("supervisor_module", Path(__file__).with_name("supervisor.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load supervisor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


supervisor = load_supervisor_module()


DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_PICK = 1
DEFAULT_CONFIG_PATH = Path("config/engine_config.json")
REQUIRED_COVERAGE_PREFIXES = ("T01", "T02", "T03", "T04")
PAYLOAD_KEY_BY_AGENT = {
    "control_planner": "plan",
    "collector_engineer": "collector_design",
    "evidence_engineer": "evidence_design",
    "security_hardening": "hardening_plan",
    "qa_validation": "validation_plan",
    "documentation_generator": "documentation_plan",
}
PAYLOAD_SUBKEYS_BY_AGENT = {
    "control_planner": ["control_decisions", "architecture_constraints", "bsi_mapping_notes"],
    "collector_engineer": ["connectors", "execution_plan", "evidence_contracts"],
    "evidence_engineer": ["evidence_models", "integrity_chain", "retention_export"],
    "security_hardening": ["baseline_items", "isolation_controls", "key_management_controls"],
    "qa_validation": ["test_matrix", "acceptance_criteria", "blocking_findings"],
    "documentation_generator": ["documents", "audience", "delivery_notes"],
}
ADDITIVE_CHANGE_TYPES = {"add_field", "append_list_item", "add_dependency", "add_module_interface"}
AUTO_APPLY_MAX_CHANGES = 5


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_task_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "tasks": {}}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {"schema_version": 1, "tasks": {}}
    payload.setdefault("schema_version", 1)
    payload.setdefault("tasks", {})
    return payload


def append_decision_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def load_engine_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config file: {config_path}")
    payload = load_json(config_path)
    if not isinstance(payload, dict):
        raise ValueError("Engine config must be a JSON object")
    payload.setdefault("openai_api_key_env", "OPENAI_API_KEY")
    payload.setdefault("models", {})
    return payload


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def get_api_key(config: dict[str, Any]) -> str:
    env_name = str(config.get("openai_api_key_env", "OPENAI_API_KEY"))
    env_overrides = parse_env_file(Path(".env"))
    if env_name in os.environ:
        return os.environ[env_name]
    if env_name in env_overrides:
        return env_overrides[env_name]
    raise RuntimeError(f"Missing API key: set {env_name} in environment or .env")


def call_model_http(api_key: str, model: str, system_prompt: str, work_item: dict[str, Any], task_id: str) -> str:
    user_prompt = (
        "Return ONLY JSON for this task output. "
        "Follow the assigned agent schema exactly and include required envelope fields.\n"
        f"task_id={task_id}\n"
        + json.dumps(work_item, ensure_ascii=False)
    )
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI connection error: {exc}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI response missing choices")
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        merged = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        if merged:
            return merged
    raise RuntimeError("OpenAI response missing text content")


def parse_model_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(text[start : end + 1])
        if isinstance(payload, dict):
            return payload
    raise ValueError("Model output is not valid JSON object")


def deterministic_files(task_id: str, agent: str) -> list[str]:
    slug = task_id.lower()
    if agent == "documentation_generator":
        return [f"docs/{slug}/deliverable.md"]
    if agent == "collector_engineer":
        return [f"modules/{slug}/collector_design.json"]
    if agent == "qa_validation":
        return [f"data/{slug}/qa_validation_report.json"]
    return [f"work_outputs/{task_id}.artifacts/{agent}_payload.json"]


def envelope_path_for(task_id: str) -> Path:
    return Path("work_outputs") / f"{task_id}.envelope.json"


def build_envelope_payload(task: dict[str, Any], status: str, errors: list[str] | None = None) -> dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "module_id": task["module_id"],
        "assigned_agent": task["assigned_agent"],
        "run_status": status,
        "errors": [str(item) for item in (errors or [])],
        "generated_at": utc_now(),
        "retryable": status != "ok",
    }


def build_agent_payload(agent: str, model_payload: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    payload_key = PAYLOAD_KEY_BY_AGENT[agent]
    subkeys = PAYLOAD_SUBKEYS_BY_AGENT[agent]

    incoming = model_payload.get(payload_key)
    result: dict[str, Any] = {}
    if isinstance(incoming, dict):
        for key in subkeys:
            value = incoming.get(key)
            if isinstance(value, list) and value:
                result[key] = [str(item) for item in value]
            else:
                result[key] = [f"{task['task_id']}:{key}:pending_detail"]
    else:
        for key in subkeys:
            result[key] = [f"{task['task_id']}:{key}:pending_detail"]
    return {payload_key: result}


def should_include_required_coverage(task_id: str) -> bool:
    return any(task_id.startswith(prefix) for prefix in REQUIRED_COVERAGE_PREFIXES)


def build_output_payload(
    task: dict[str, Any],
    module: dict[str, Any],
    model_payload: dict[str, Any],
    status: str,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    agent = task["assigned_agent"]
    payload: dict[str, Any] = {
        "task_id": task["task_id"],
        "module_id": task["module_id"],
        "assigned_agent": agent,
        "status": status,
        "summary": str(model_payload.get("summary") or f"Generated output for {task['task_id']}"),
        "produced_files": deterministic_files(task["task_id"], agent),
        "notes": [str(note) for note in model_payload.get("notes", []) if isinstance(note, str)],
        "errors": [str(item) for item in (errors or [])],
    }

    payload.update(build_agent_payload(agent, model_payload, task))

    if should_include_required_coverage(task["task_id"]):
        payload["coverage_claims"] = {
            "controls": [str(item) for item in task.get("control_scope", [])] or ["unknown_control"],
            "modules": [str(task.get("module_id") or "unknown_module")],
            "bsi_domains": [str(item) for item in module.get("bsi_domains", [])] or ["unknown_bsi_domain"],
        }
    elif isinstance(model_payload.get("coverage_claims"), dict):
        claims = model_payload["coverage_claims"]
        payload["coverage_claims"] = {
            "controls": [str(x) for x in claims.get("controls", []) if isinstance(x, str)],
            "modules": [str(x) for x in claims.get("modules", []) if isinstance(x, str)],
            "bsi_domains": [str(x) for x in claims.get("bsi_domains", []) if isinstance(x, str)],
        }

    if status == "ok":
        payload["errors"] = []
    return payload


def run_command(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    combined = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, combined.strip()


def mark_needs_input(task_id: str, error_text: str, task_status_path: Path, decision_log_path: Path) -> None:
    task_status = load_task_status(task_status_path)
    record = task_status.setdefault("tasks", {}).setdefault(task_id, {})
    attempts = int(record.get("attempts", 0)) + 1
    record["state"] = "needs_input"
    record["last_error"] = error_text
    record["attempts"] = attempts
    record["last_updated"] = utc_now()

    task_status_path.parent.mkdir(parents=True, exist_ok=True)
    task_status_path.write_text(stable_dump(task_status), encoding="utf-8")

    append_decision_log(
        decision_log_path,
        {
            "event": "engine_validation_failed",
            "timestamp": utc_now(),
            "task_id": task_id,
            "state": "needs_input",
            "attempts": attempts,
            "last_error": error_text,
        },
    )


def select_and_prepare(plan_path: Path, task_status_path: Path, decision_log_path: Path, pick: int, dry_run: bool) -> list[dict[str, Any]]:
    plan = load_json(plan_path)
    task_graph = plan.get("task_graph", [])
    module_phase = supervisor.infer_module_phase(plan)
    downstream_map = supervisor.build_downstream_map(task_graph)

    task_status = load_task_status(task_status_path)
    supervisor.ensure_task_records(task_status, task_graph)

    candidates = supervisor.select_unblocked_tasks(task_graph, task_status)
    ranked = sorted(candidates, key=lambda task: supervisor.task_score(task, module_phase, downstream_map), reverse=True)
    picked = ranked[: max(pick, 0)]

    if not picked:
        return []

    timestamp = utc_now()
    for task in picked:
        task_id = task["task_id"]
        record = task_status["tasks"][task_id]
        if supervisor.normalize_state(record.get("state")) == "pending":
            record["state"] = "assigned"
            record["last_updated"] = timestamp

        rc = supervisor.run_agent_runner(task_id, dry_run=dry_run)
        if rc != 0:
            raise RuntimeError(f"agent_runner failed for task {task_id}")

        append_decision_log(
            decision_log_path,
            {
                "event": "engine_task_selected",
                "timestamp": timestamp,
                "task_id": task_id,
                "dry_run": dry_run,
            },
        )

    task_status_path.parent.mkdir(parents=True, exist_ok=True)
    task_status_path.write_text(stable_dump(task_status), encoding="utf-8")
    return picked


def maybe_auto_apply_architecture(enabled: bool) -> None:
    if not enabled:
        return

    rc, out = run_command([sys.executable, "scripts/reconcile_architecture.py", "--mode", "propose"])
    if rc != 0:
        print("architecture reconcile propose failed")
        print(out)
        return

    diff_path: Path | None = None
    for line in out.splitlines():
        if line.startswith("diff="):
            diff_path = Path(line.split("=", 1)[1].strip())
            break

    if diff_path is None or not diff_path.exists():
        print("auto-apply skipped: no diff output found")
        return

    diff_payload = load_json(diff_path)
    changes = diff_payload.get("changes", []) if isinstance(diff_payload, dict) else []
    if not isinstance(changes, list):
        print("auto-apply skipped: malformed diff")
        return

    additive_only = all(isinstance(change, dict) and change.get("type") in ADDITIVE_CHANGE_TYPES for change in changes)
    if additive_only and len(changes) <= AUTO_APPLY_MAX_CHANGES:
        rc_apply, out_apply = run_command([sys.executable, "scripts/reconcile_architecture.py", "--mode", "apply"])
        if rc_apply != 0:
            print("auto-apply failed")
            print(out_apply)
        else:
            print("auto-apply complete")
    else:
        print(f"auto-apply skipped: additive_only={additive_only} changes={len(changes)}")


def run_cycle(args: argparse.Namespace) -> int:
    plan_path = Path("architecture_plan.json")
    task_status_path = Path("state/task_status.json")
    decision_log_path = Path("state/decision_log.jsonl")

    picked = select_and_prepare(plan_path, task_status_path, decision_log_path, args.pick, args.dry_run)
    print(f"Cycle selected {len(picked)} task(s)")
    if not picked:
        return 0

    if args.dry_run:
        for task in picked:
            print(f"[dry-run] would execute model + validate/promote for {task['task_id']}")
        return 0

    config = load_engine_config(Path(args.config))
    api_key = get_api_key(config)
    model_map = config.get("models", {}) if isinstance(config.get("models"), dict) else {}

    plan = load_json(plan_path)
    modules = {
        module.get("module_id"): module
        for module in plan.get("architecture_summary", {}).get("core_modules", [])
        if isinstance(module, dict) and isinstance(module.get("module_id"), str)
    }

    for task in picked:
        task_id = task["task_id"]
        work_item_path = Path("work_items") / f"{task_id}.input.json"
        output_path = Path("work_outputs") / f"{task_id}.output.json"
        envelope_path = envelope_path_for(task_id)

        work_item = load_json(work_item_path)
        assigned_agent = task.get("assigned_agent", "")
        prompt_path = Path("prompts") / f"{assigned_agent}_system.txt"
        system_prompt = prompt_path.read_text(encoding="utf-8")

        model_name = model_map.get(assigned_agent)
        if not isinstance(model_name, str) or not model_name.strip():
            raise RuntimeError(f"Missing model mapping for agent '{assigned_agent}'")

        try:
            raw = call_model_http(api_key, model_name, system_prompt, work_item, task_id)
            parsed = parse_model_json(raw)
            payload = build_output_payload(task, modules.get(task.get("module_id"), {}), parsed, status="ok")
        except Exception as exc:
            payload = build_output_payload(
                task,
                modules.get(task.get("module_id"), {}),
                {"summary": f"Model error for {task_id}", "notes": []},
                status="needs_input",
                errors=[str(exc)],
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(stable_dump(payload), encoding="utf-8")
        envelope_path.write_text(
            stable_dump(build_envelope_payload(task, status=payload.get("status", "error"), errors=payload.get("errors", []))),
            encoding="utf-8",
        )

        rc_val, out_val = run_command([sys.executable, "scripts/validate_output.py", str(output_path)])
        if rc_val != 0:
            mark_needs_input(task_id, out_val or "validator failed", task_status_path, decision_log_path)
            print(f"validation failed for {task_id}")
            continue

        rc_promote, out_promote = run_command([sys.executable, "scripts/promote_output.py", "--task-id", task_id])
        if rc_promote != 0:
            mark_needs_input(task_id, out_promote or "promote failed", task_status_path, decision_log_path)
            print(f"promotion failed for {task_id}")
            continue

    rc_cov, out_cov = run_command([sys.executable, "scripts/generate_coverage.py"])
    if rc_cov != 0:
        print(out_cov)
        return rc_cov

    rc_rec, out_rec = run_command([sys.executable, "scripts/reconcile_architecture.py", "--mode", "propose"])
    if rc_rec != 0:
        print(out_rec)
        return rc_rec

    if args.auto_apply_architecture:
        maybe_auto_apply_architecture(enabled=True)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous loop runner for full self-expanding cycle")
    parser.add_argument("--once", action="store_true", help="Run a single cycle (default)")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--pick", type=int, default=DEFAULT_PICK)
    parser.add_argument("--dry-run", action="store_true", help="Select tasks and print planned actions only")
    parser.add_argument("--auto-apply-architecture", action="store_true", help="Auto-apply small additive reconciliation changes")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to engine config JSON")
    args = parser.parse_args()

    run_once = args.once or not args.loop
    if run_once:
        return run_cycle(args)

    while True:
        rc = run_cycle(args)
        if rc != 0:
            return rc
        time.sleep(max(1, args.interval_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
