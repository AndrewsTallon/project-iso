#!/usr/bin/env python3
"""Smoke tests for validate_output.py contract/envelope behavior."""

from __future__ import annotations

import subprocess
import sys
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
    valid = "tests/contracts/control_planner.valid.output.json"
    invalid_extra = "tests/contracts/control_planner.invalid_extra_root.output.json"
    envelope = "tests/contracts/control_planner.envelope.json"

    valid_result = run("scripts/validate_output.py", valid)
    missing_jsonschema = "Missing dependency: jsonschema" in f"{valid_result.stdout}\n{valid_result.stderr}"

    if missing_jsonschema:
        # Environment fallback: mirror the intended unknown-root behavior via contract_guard.
        assert_ok(run("scripts/contract_guard.py", valid), "valid contract fixture (fallback)")
        assert_fail(
            run("scripts/contract_guard.py", invalid_extra),
            "extra root key fixture (fallback)",
            "includes unknown root keys",
        )
    else:
        assert_ok(valid_result, "valid contract fixture")
        assert_fail(
            run("scripts/validate_output.py", invalid_extra),
            "extra root key fixture",
            "does not match",
        )

    assert_fail(
        run("scripts/validate_output.py", envelope),
        "envelope fixture validated as contract",
        "no *.output.json files found",
    )

    print("Smoke validate_output contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
