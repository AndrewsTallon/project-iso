#!/usr/bin/env python3
"""Validate agent output JSON files against strict schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_BY_AGENT = {
    "control_planner": "schemas/control_planner_output.schema.json",
    "collector_engineer": "schemas/collector_engineer_output.schema.json",
    "evidence_engineer": "schemas/evidence_engineer_output.schema.json",
    "security_hardening": "schemas/security_hardening_output.schema.json",
    "qa_validation": "schemas/qa_validation_output.schema.json",
    "documentation_generator": "schemas/documentation_generator_output.schema.json",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema(schema_path: Path) -> dict[str, Any]:
    schema = load_json(schema_path)
    if "allOf" not in schema:
        return schema

    resolved_all_of = []
    for item in schema["allOf"]:
        ref = item.get("$ref")
        if ref == "agent_envelope.schema.json":
            resolved_all_of.append(load_json(schema_path.parent / ref))
        else:
            resolved_all_of.append(item)
    schema["allOf"] = resolved_all_of
    return schema


def validate_file(output_path: Path, agent: str | None) -> int:
    if not output_path.name.endswith(".output.json"):
        print(f"FAIL: only *.output.json files are supported: {output_path}")
        return 1
    try:
        from jsonschema.validators import Draft202012Validator
    except ImportError:
        print("Missing dependency: jsonschema. Install it before validating outputs.")
        return 1

    payload = load_json(output_path)
    assigned_agent = agent or payload.get("assigned_agent")
    if assigned_agent not in SCHEMA_BY_AGENT:
        print(f"Unknown agent '{assigned_agent}'. Use --agent with one of: {', '.join(sorted(SCHEMA_BY_AGENT))}")
        return 1

    schema_path = Path(SCHEMA_BY_AGENT[assigned_agent])
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)

    if errors:
        print(f"FAIL: {output_path} does not match {schema_path}")
        for error in errors:
            path = ".".join(str(p) for p in error.absolute_path) or "<root>"
            print(f" - {path}: {error.message}")
        return 1

    print(f"PASS: {output_path} matches {schema_path}")
    return 0




def validate_output(output_path: Path, agent: str | None) -> int:
    """Backward-compatible function name used by promotion flow."""
    return validate_file(output_path, agent)
def iter_json_files(target: Path, recursive: bool) -> list[Path]:
    if target.is_file():
        return [target] if target.name.endswith(".output.json") else []

    if recursive:
        return sorted(path for path in target.glob("**/*.output.json") if path.is_file())

    discovered = [path for path in target.glob("*.output.json") if path.is_file()]
    contracts_dir = target / "contracts"
    if contracts_dir.is_dir():
        discovered.extend(path for path in contracts_dir.glob("*.output.json") if path.is_file())
    return sorted(set(discovered))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate agent output JSON file(s).")
    parser.add_argument("output", help="Path to output JSON file or directory")
    parser.add_argument("--agent", help="Explicit agent type override")
    parser.add_argument("--recursive", action="store_true", help="Recursively validate all JSON files under a directory")
    args = parser.parse_args()

    target = Path(args.output)
    if not target.exists():
        print(f"FAIL: target does not exist: {target}")
        return 1

    files = iter_json_files(target, recursive=args.recursive)
    if not files:
        print(f"FAIL: no *.output.json files found for target: {target}")
        return 1

    code = 0
    for file_path in files:
        code |= validate_file(file_path, args.agent)
    return code


if __name__ == "__main__":
    sys.exit(main())
