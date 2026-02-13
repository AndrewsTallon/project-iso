#!/usr/bin/env python3
"""Smoke tests for contract_guard.py unknown-root and envelope scanning policy."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def assert_ok(result: subprocess.CompletedProcess[str], context: str) -> None:
    if result.returncode != 0:
        raise AssertionError(
            f"{context} should pass but failed with rc={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def assert_fail(result: subprocess.CompletedProcess[str], context: str, expected: str) -> None:
    if result.returncode == 0:
        raise AssertionError(f"{context} should fail but passed\nstdout:\n{result.stdout}")
    combined = f"{result.stdout}\n{result.stderr}"
    if expected not in combined:
        raise AssertionError(
            f"{context} did not include expected text {expected!r}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def main() -> int:
    valid = ROOT / "tests/contracts/control_planner.valid.output.json"
    invalid_extra = ROOT / "tests/contracts/control_planner.invalid_extra_root.output.json"
    envelope = ROOT / "tests/contracts/control_planner.envelope.json"

    assert_ok(
        run("scripts/contract_guard.py", str(valid)),
        "valid contract fixture",
    )
    assert_fail(
        run("scripts/contract_guard.py", str(invalid_extra)),
        "extra root key fixture",
        "includes unknown root keys",
    )

    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        (temp_dir / valid.name).write_text(valid.read_text(encoding="utf-8"), encoding="utf-8")
        (temp_dir / invalid_extra.name).write_text(invalid_extra.read_text(encoding="utf-8"), encoding="utf-8")
        (temp_dir / envelope.name).write_text(envelope.read_text(encoding="utf-8"), encoding="utf-8")

        scanned = run("scripts/contract_guard.py", str(temp_dir))
        assert_fail(scanned, "directory scan with mixed files", "includes unknown root keys")
        if envelope.name in f"{scanned.stdout}\n{scanned.stderr}":
            raise AssertionError("envelope file was not ignored during contract-only scan")

    print("Smoke contract_guard contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
