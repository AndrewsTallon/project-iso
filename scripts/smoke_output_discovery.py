#!/usr/bin/env python3
"""Smoke test for output discovery conventions."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stable_dump(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    validate_module = load_module(ROOT / "scripts" / "validate_output.py", "validate_output_module")
    guard_module = load_module(ROOT / "scripts" / "contract_guard.py", "contract_guard_module")

    with tempfile.TemporaryDirectory() as tmp:
        temp_root = Path(tmp)
        outputs_dir = temp_root / "work_outputs"
        contracts_dir = outputs_dir / "contracts"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        contracts_dir.mkdir(parents=True, exist_ok=True)

        output_payload = {
            "task_id": "T01_smoke",
            "module_id": "mod_smoke",
            "assigned_agent": "control_planner",
            "status": "ok",
            "summary": "Smoke output",
            "produced_files": [],
            "notes": [],
            "errors": [],
            "coverage_claims": {
                "controls": ["ISO27001:A.5.1"],
                "modules": ["mod_smoke"],
                "bsi_domains": ["ISMS"],
            },
            "plan": {
                "control_decisions": ["Keep deterministic checks"],
                "architecture_constraints": ["No runtime randomness"],
                "bsi_mapping_notes": ["Maps to ISMS domain"],
            },
        }

        (outputs_dir / "T01_smoke.output.json").write_text(stable_dump(output_payload), encoding="utf-8")
        (outputs_dir / "T01_smoke.envelope.json").write_text(
            stable_dump({"unknown_operational_key": "ignored", "retry_count": 3}), encoding="utf-8"
        )
        (contracts_dir / "T99_split.output.json").write_text(stable_dump(output_payload), encoding="utf-8")

        discovered_validate = validate_module.iter_json_files(outputs_dir, recursive=False)
        discovered_guard = guard_module.iter_targets(outputs_dir)

        validate_names = [path.name for path in discovered_validate]
        guard_names = [path.name for path in discovered_guard]

        if "T01_smoke.envelope.json" in validate_names or "T01_smoke.envelope.json" in guard_names:
            raise AssertionError("Envelope file was discovered by contract tooling")
        if "T01_smoke.output.json" not in validate_names or "T01_smoke.output.json" not in guard_names:
            raise AssertionError("Primary output file missing from discovery")
        if "T99_split.output.json" not in validate_names or "T99_split.output.json" not in guard_names:
            raise AssertionError("contracts/ split output file missing from discovery")

    print("Smoke output discovery: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
