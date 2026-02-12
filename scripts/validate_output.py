#!/usr/bin/env python3
"""Validate an agent output JSON file against strict schemas."""

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


def validate_output(output_path: Path, agent: str | None) -> int:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an agent output JSON file.")
    parser.add_argument("output", help="Path to output JSON file")
    parser.add_argument("--agent", help="Explicit agent type override")
    args = parser.parse_args()
    return validate_output(Path(args.output), args.agent)


if __name__ == "__main__":
    sys.exit(main())
