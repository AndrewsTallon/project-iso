#!/usr/bin/env python3
"""Minimal deterministic runtime orchestrator for offline evidence runs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.collectors.linux_inventory import collect
from runtime.checks.inventory_checks import asset_inventory_recorded


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")


def run_once(config_path: Path) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    run_id = utc_run_id()
    output_root = Path(config["output_root"])

    evidence_dir = output_root / "evidence" / run_id / "linux_inventory" / "normalized"
    checks_dir = output_root / "checks" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    checks_dir.mkdir(parents=True, exist_ok=True)

    inventory = collect(run_id=run_id)
    inventory_path = evidence_dir / "inventory.json"
    inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    result = asset_inventory_recorded(run_id=run_id, inventory=inventory)
    result_path = checks_dir / "asset_inventory_recorded.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    checkpoint = output_root / "runs" / f"{run_id}.json"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "ok",
                "evidence_files": [str(inventory_path)],
                "check_files": [str(result_path)],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return checkpoint


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="runtime/config/runtime_config.json")
    args = parser.parse_args()

    checkpoint = run_once(Path(args.config))
    print(f"run complete: {checkpoint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
