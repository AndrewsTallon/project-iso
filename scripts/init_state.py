#!/usr/bin/env python3
"""Initialize persistent state files for the self-expanding execution loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STATE_DIR = Path("state")

INITIAL_STATE_FILES: dict[str, Any] = {
    "task_status.json": {
        "schema_version": 1,
        "tasks": {},
    },
    "coverage.json": {
        "schema_version": 1,
        "generated_at": "",
        "by_control": {},
        "by_module": {},
        "by_bsi_domain": {},
        "overall": {
            "controls_total": 0,
            "controls_with_tasks": 0,
            "controls_unknown": 0,
            "controls_planned": 0,
            "controls_in_progress": 0,
            "controls_accepted": 0,
            "controls_validated": 0,
            "modules_total": 0,
            "modules_validated": 0,
            "bsi_domains_total": 0,
            "bsi_domains_validated": 0,
            "work_outputs_total": 0,
        },
        "gaps": {
            "top_modules_blocked": [],
            "top_iso_controls_missing": [],
            "top_bsi_domains_missing": [],
        },
    },
    "module_registry.json": {
        "schema_version": 1,
        "modules": {},
    },
    "run_history.json": {
        "schema_version": 1,
        "runs": [],
    },
    "decision_log.jsonl": "",
}


def stable_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def init_state(root: Path, force: bool = False) -> list[str]:
    state_dir = root / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    for file_name, template in INITIAL_STATE_FILES.items():
        target = state_dir / file_name
        if target.exists() and not force:
            continue

        if file_name.endswith(".jsonl"):
            target.write_text("", encoding="utf-8")
        else:
            target.write_text(stable_dump(template), encoding="utf-8")
        created.append(file_name)

    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize state/ files if missing.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing state files.")
    args = parser.parse_args()

    created = init_state(Path("."), force=args.force)
    if created:
        print("Initialized:")
        for file_name in created:
            print(f" - state/{file_name}")
    else:
        print("State already initialized. No files changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
