#!/usr/bin/env python3
"""Enforce root-level JSON contracts by rejecting unknown keys.

This script is intentionally strict and deterministic. It is designed to catch
schema drift early (for example, agent outputs with extra root keys).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_BY_AGENT = {
    "control_planner": Path("schemas/control_planner_output.schema.json"),
    "collector_engineer": Path("schemas/collector_engineer_output.schema.json"),
    "evidence_engineer": Path("schemas/evidence_engineer_output.schema.json"),
    "security_hardening": Path("schemas/security_hardening_output.schema.json"),
    "qa_validation": Path("schemas/qa_validation_output.schema.json"),
    "documentation_generator": Path("schemas/documentation_generator_output.schema.json"),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_allowed_keys(schema: dict[str, Any]) -> set[str]:
    keys: set[str] = set(schema.get("properties", {}).keys())
    for part in schema.get("allOf", []):
        if "$ref" in part and part["$ref"] == "agent_envelope.schema.json":
            ref_schema = load_json(Path("schemas") / part["$ref"])
            keys.update(ref_schema.get("properties", {}).keys())
        else:
            keys.update(part.get("properties", {}).keys())
    return keys


def guard_file(path: Path) -> int:
    if not path.name.endswith(".output.json"):
        print(f"FAIL: only *.output.json files are supported: {path}")
        return 1
    payload = load_json(path)
    if not isinstance(payload, dict):
        print(f"FAIL: {path} root must be an object")
        return 1

    assigned_agent = payload.get("assigned_agent")
    if assigned_agent not in SCHEMA_BY_AGENT:
        print(f"FAIL: {path} has unknown assigned_agent={assigned_agent!r}")
        return 1

    schema = load_json(SCHEMA_BY_AGENT[assigned_agent])
    allowed_keys = _collect_allowed_keys(schema)
    unknown = sorted(set(payload.keys()) - allowed_keys)
    if unknown:
        print(f"FAIL: {path} includes unknown root keys: {', '.join(unknown)}")
        return 1

    print(f"PASS: {path} root keys match contract")
    return 0


def iter_targets(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.name.endswith(".output.json") else []

    discovered = [path for path in target.glob("*.output.json") if path.is_file()]
    contracts_dir = target / "contracts"
    if contracts_dir.is_dir():
        discovered.extend(path for path in contracts_dir.glob("*.output.json") if path.is_file())
    return sorted(set(discovered))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject unknown JSON root keys for agent outputs")
    parser.add_argument("target", help="JSON file or directory of JSON files")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"FAIL: target does not exist: {target}")
        return 1

    files = iter_targets(target)
    if not files:
        print(f"FAIL: no *.output.json files found for target: {target}")
        return 1

    code = 0
    for file_path in files:
        code |= guard_file(file_path)
    return code


if __name__ == "__main__":
    sys.exit(main())
