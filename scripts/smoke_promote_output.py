#!/usr/bin/env python3
"""Smoke test for deterministic output promotion."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def stable_dump(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        temp_root = Path(tmp)
        state_dir = temp_root / "state"
        outputs_dir = temp_root / "work_outputs"
        state_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)

        task_status = {
            "schema_version": 1,
            "tasks": {
                "T01_smoke": {
                    "module_id": "mod_smoke",
                    "state": "assigned",
                    "last_updated": "",
                }
            },
        }

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

        task_status_path = state_dir / "task_status.json"
        output_path = outputs_dir / "T01_smoke.output.json"
        task_status_path.write_text(stable_dump(task_status), encoding="utf-8")
        output_path.write_text(stable_dump(output_payload), encoding="utf-8")

        cmd = [
            sys.executable,
            "scripts/promote_output.py",
            "--task-id",
            "T01_smoke",
            "--task-status",
            str(task_status_path),
            "--output",
            str(output_path),
        ]
        proc = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            return proc.returncode

        updated = json.loads(task_status_path.read_text(encoding="utf-8"))
        record = updated["tasks"]["T01_smoke"]
        if record.get("state") != "accepted":
            raise AssertionError("Expected state to be accepted after promotion")
        if record.get("output_path") != output_path.as_posix():
            raise AssertionError("Expected output_path to be recorded")
        if not record.get("output_sha256"):
            raise AssertionError("Expected output_sha256 to be recorded")

    print("Smoke promote output: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
