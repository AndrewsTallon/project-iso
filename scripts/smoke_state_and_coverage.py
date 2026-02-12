#!/usr/bin/env python3
"""Smoke test for state initialization and coverage generation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> int:
    run([sys.executable, "scripts/init_state.py"])
    run([sys.executable, "scripts/generate_coverage.py"])

    coverage = json.loads((ROOT / "state/coverage.json").read_text(encoding="utf-8"))
    required_keys = {"schema_version", "by_control", "by_module", "by_bsi_domain", "overall", "gaps"}
    missing = required_keys - set(coverage)
    if missing:
        print(f"Missing keys from state/coverage.json: {sorted(missing)}")
        return 1

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
