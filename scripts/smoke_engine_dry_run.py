#!/usr/bin/env python3
"""Smoke test for engine dry-run mode."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    before = {p: p.stat().st_mtime for p in Path("work_items").glob("*.input.json")}
    start = time.time()

    proc = subprocess.run(
        [sys.executable, "scripts/engine.py", "--dry-run", "--once"],
        check=False,
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise AssertionError("engine dry-run failed")

    output = (proc.stdout or "") + (proc.stderr or "")
    if "Cycle selected" not in output:
        raise AssertionError("engine output did not indicate task selection")

    touched = []
    for path in Path("work_items").glob("*.input.json"):
        previous = before.get(path, 0.0)
        if path.stat().st_mtime >= max(start - 1.0, previous):
            touched.append(path)

    if not touched:
        raise AssertionError("engine dry-run did not create/update any work_item")

    print(f"PASS: engine dry-run touched {len(touched)} work_item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
