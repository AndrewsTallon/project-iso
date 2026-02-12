#!/usr/bin/env python3
"""Smoke test for architecture reconciliation propose mode with no eligible outputs."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def stable_dump(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        architecture = {
            "architecture_summary": {"core_modules": []},
            "task_graph": [
                {
                    "task_id": "T01_example",
                    "module_id": "mod_example",
                    "blocking_dependencies": [],
                }
            ],
        }
        task_status = {"schema_version": 1, "tasks": {}}

        (root / "work_outputs").mkdir(parents=True, exist_ok=True)
        (root / "state").mkdir(parents=True, exist_ok=True)
        (root / "architecture_plan.json").write_text(stable_dump(architecture), encoding="utf-8")
        (root / "state" / "task_status.json").write_text(stable_dump(task_status), encoding="utf-8")

        cmd = [
            sys.executable,
            "scripts/reconcile_architecture.py",
            "--mode",
            "propose",
            "--architecture",
            str(root / "architecture_plan.json"),
            "--task-status",
            str(root / "state" / "task_status.json"),
            "--work-outputs",
            str(root / "work_outputs"),
            "--out-dir",
            str(root / "architecture" / "proposals"),
            "--decision-log",
            str(root / "state" / "decision_log.jsonl"),
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            raise SystemExit(proc.returncode)

        proposal_dir = root / "architecture" / "proposals"
        diff_files = sorted(proposal_dir.glob("*_architecture_plan.diff.json"))
        next_files = sorted(proposal_dir.glob("*_architecture_plan.next.json"))
        if len(diff_files) != 1 or len(next_files) != 1:
            raise AssertionError("Expected exactly one proposal and one diff artifact")

        diff_payload = json.loads(diff_files[0].read_text(encoding="utf-8"))
        if diff_payload.get("changes") != []:
            raise AssertionError("Expected zero reconciliation changes for empty accepted outputs")

    print("Smoke reconcile architecture: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
