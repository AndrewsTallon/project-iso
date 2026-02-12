#!/usr/bin/env python3
"""Regression smoke test: supervisor selects pending, unblocked task in dry-run."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def stable_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="supervisor smoke ") as tmp:
        root = Path(tmp)
        state_dir = root / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        plan = {
            "task_graph": [
                {
                    "task_id": "T01_platform_blueprint",
                    "module_id": "M01",
                    "blocking_dependencies": [],
                }
            ],
            "implementation_phases": [
                {
                    "phase": "MVP",
                    "focus_modules": ["M01"],
                }
            ],
        }
        task_status = {
            "schema_version": 1,
            "tasks": {
                "T01_platform_blueprint": {
                    "state": "pending",
                    "module_id": "M01",
                }
            },
        }

        plan_path = root / "architecture_plan.json"
        task_status_path = state_dir / "task_status.json"
        run_history_path = state_dir / "run_history.json"
        decision_log_path = state_dir / "decision_log.jsonl"

        plan_path.write_text(stable_dump(plan), encoding="utf-8")
        task_status_path.write_text(stable_dump(task_status), encoding="utf-8")

        proc = subprocess.run(
            [
                sys.executable,
                "scripts/supervisor.py",
                "--dry-run",
                "--explain-selection",
                "--plan",
                str(plan_path),
                "--task-status",
                str(task_status_path),
                "--run-history",
                str(run_history_path),
                "--decision-log",
                str(decision_log_path),
                "--pick",
                "1",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            raise AssertionError("supervisor dry-run failed")

        output = (proc.stdout or "") + (proc.stderr or "")
        if "Would select: ['T01_platform_blueprint']" not in output:
            raise AssertionError(f"supervisor did not report selected pending task:\n{output}")
        if "Selected T01_platform_blueprint" not in output:
            raise AssertionError(f"supervisor did not execute selection:\n{output}")

    print("PASS: supervisor selects pending unblocked task")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
