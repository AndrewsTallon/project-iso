#!/usr/bin/env python3
"""Promote schema-valid task outputs into accepted state with deterministic gates."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_COVERAGE_PREFIXES = ("T01", "T02", "T03", "T04")


def stable_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_validate_module(script_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("validate_output_module", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load validator script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEMA_BY_AGENT = {
    "control_planner": "control_planner_output.schema.json",
    "collector_engineer": "collector_engineer_output.schema.json",
    "evidence_engineer": "evidence_engineer_output.schema.json",
    "security_hardening": "security_hardening_output.schema.json",
    "qa_validation": "qa_validation_output.schema.json",
    "documentation_generator": "documentation_generator_output.schema.json",
}


def _validate_by_schema(payload: Any, schema: dict[str, Any], schema_dir: Path, path: str = "<root>") -> list[str]:
    errors: list[str] = []

    if "allOf" in schema:
        for idx, item in enumerate(schema.get("allOf", [])):
            if isinstance(item, dict) and "$ref" in item:
                ref_schema = load_json(schema_dir / item["$ref"])
                errors.extend(_validate_by_schema(payload, ref_schema, schema_dir, path))
            else:
                errors.extend(_validate_by_schema(payload, item, schema_dir, path))

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(payload, dict):
            return [f"{path}: expected object"]

        required = schema.get("required", [])
        for key in required:
            if key not in payload:
                errors.append(f"{path}: missing required key '{key}'")

        properties = schema.get("properties", {})
        for key, value in payload.items():
            if key in properties:
                child_path = f"{path}.{key}" if path != "<root>" else key
                errors.extend(_validate_by_schema(value, properties[key], schema_dir, child_path))

    elif expected_type == "array":
        if not isinstance(payload, list):
            return [f"{path}: expected array"]
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(payload):
                errors.extend(_validate_by_schema(item, item_schema, schema_dir, f"{path}[{idx}]"))
        if schema.get("uniqueItems"):
            unique = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in payload}
            if len(unique) != len(payload):
                errors.append(f"{path}: array items must be unique")

    elif expected_type == "string":
        if not isinstance(payload, str):
            return [f"{path}: expected string"]
        if "minLength" in schema and len(payload) < int(schema["minLength"]):
            errors.append(f"{path}: minimum length is {schema['minLength']}")
        if "pattern" in schema and re.match(schema["pattern"], payload) is None:
            errors.append(f"{path}: does not match required pattern")

    if "enum" in schema and payload not in schema["enum"]:
        errors.append(f"{path}: value {payload!r} not in enum")
    if "const" in schema and payload != schema["const"]:
        errors.append(f"{path}: expected const value {schema['const']!r}")

    return errors


def fallback_validate_schema(payload: dict[str, Any], schema_dir: Path, agent: str | None) -> None:
    assigned_agent = agent or payload.get("assigned_agent")
    if assigned_agent not in SCHEMA_BY_AGENT:
        raise ValueError(f"Unknown agent '{assigned_agent}'")
    schema = load_json(schema_dir / SCHEMA_BY_AGENT[assigned_agent])
    errors = _validate_by_schema(payload, schema, schema_dir)
    if errors:
        raise ValueError("Schema validation failed: " + "; ".join(errors[:5]))


def validate_schema(output_path: Path, output_payload: dict[str, Any], schema_dir: Path, agent: str | None) -> None:
    module = load_validate_module(Path("scripts/validate_output.py"))
    code = module.validate_output(output_path, agent)
    if code != 0:
        fallback_validate_schema(output_payload, schema_dir, agent)


def task_needs_required_coverage(task_id: str) -> bool:
    return any(task_id.startswith(prefix) for prefix in REQUIRED_COVERAGE_PREFIXES)


def ensure_required_coverage(payload: dict[str, Any], task_id: str) -> None:
    if not task_needs_required_coverage(task_id):
        return

    claims = payload.get("coverage_claims")
    if not isinstance(claims, dict):
        raise ValueError("coverage_claims is required for T01/T02/T03/T04 outputs")

    for key in ("controls", "modules", "bsi_domains"):
        value = claims.get(key)
        if not isinstance(value, list) or len(value) == 0:
            raise ValueError(f"coverage_claims.{key} must be a non-empty list")


def contains_delete_semantics(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in {"delete", "deletes", "deleted", "remove", "removed", "removes"}:
                return True
            if lowered in {"op", "operation", "action", "change_type", "type"} and isinstance(child, str):
                action = child.lower().replace("_", "-")
                if action in {"delete", "remove", "removed"}:
                    return True
            if contains_delete_semantics(child):
                return True
        return False
    if isinstance(value, list):
        return any(contains_delete_semantics(item) for item in value)
    return False


def ensure_architecture_updates_allowed(output_payload: dict[str, Any], current_state: str) -> None:
    if "architecture_updates" not in output_payload:
        return
    if current_state not in {"accepted", "validated"}:
        raise ValueError("architecture_updates require current task state to be accepted or validated")
    updates = output_payload.get("architecture_updates")
    if contains_delete_semantics(updates):
        raise ValueError("architecture_updates must be additive-only (delete/remove operations are not allowed)")


def load_task_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "tasks": {}}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {"schema_version": 1, "tasks": {}}
    payload.setdefault("schema_version", 1)
    payload.setdefault("tasks", {})
    return payload


def append_run_history(path: Path, record: dict[str, Any]) -> None:
    payload: dict[str, Any] = {"schema_version": 1, "runs": []}
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
    parser = argparse.ArgumentParser(description="Promote a produced output to accepted if all gates pass.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-status", default="state/task_status.json")
    parser.add_argument("--output", help="Path to output JSON file (default: work_outputs/<task_id>.output.json)")
    parser.add_argument("--schemas-dir", default="schemas/")
    parser.add_argument("--agent", help="Optional assigned_agent override")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else Path("work_outputs") / f"{args.task_id}.output.json"
    task_status_path = Path(args.task_status)
    run_history_path = task_status_path.parent / "run_history.json"
    decision_log_path = task_status_path.parent / "decision_log.jsonl"

    output_payload = load_json(output_path)
    if not isinstance(output_payload, dict):
        print("Output payload must be a JSON object")
        return 1

    task_status = load_task_status(task_status_path)
    task_record = task_status.setdefault("tasks", {}).setdefault(args.task_id, {})
    previous_state = str(task_record.get("state", "pending"))

    validate_schema(output_path, output_payload, Path(args.schemas_dir), args.agent)

    status = output_payload.get("status")
    if status != "ok":
        raise ValueError("Output envelope status must be 'ok' for promotion")

    ensure_required_coverage(output_payload, args.task_id)
    ensure_architecture_updates_allowed(output_payload, previous_state)

    timestamp = utc_timestamp()
    output_hash = sha256_file(output_path)
    resolved_agent = args.agent or output_payload.get("assigned_agent") or task_record.get("agent") or ""

    if previous_state in {"assigned", "produced"}:
        task_record["state"] = "accepted"
    task_record["last_updated"] = timestamp
    task_record["accepted_at"] = timestamp
    task_record["output_path"] = output_path.as_posix()
    task_record["output_sha256"] = output_hash
    task_record["agent"] = resolved_agent

    task_status_path.parent.mkdir(parents=True, exist_ok=True)
    task_status_path.write_text(stable_dump(task_status), encoding="utf-8")

    run_record = {
        "event": "promote_output",
        "task_id": args.task_id,
        "timestamp": timestamp,
        "previous_state": previous_state,
        "new_state": task_record.get("state", previous_state),
        "output_path": output_path.as_posix(),
        "output_sha256": output_hash,
        "agent": resolved_agent,
        "schemas_dir": Path(args.schemas_dir).as_posix(),
    }
    append_run_history(run_history_path, run_record)
    append_decision_log(decision_log_path, run_record)

    print(f"Promoted {args.task_id}: {previous_state} -> {task_record.get('state', previous_state)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Promotion failed: {exc}")
        raise SystemExit(1)
