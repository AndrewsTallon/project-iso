#!/usr/bin/env python3
"""Preflight checks for project-iso engine and on-prem runtime execution."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]


def check_python() -> tuple[bool, str]:
    ok = sys.version_info >= (3, 10)
    return ok, f"python version {'ok' if ok else 'too old'}: {sys.version.split()[0]} (required: >=3.10)"


def check_dependency(module_name: str) -> tuple[bool, str]:
    try:
        __import__(module_name)
        return True, f"dependency available: {module_name}"
    except Exception as exc:  # pragma: no cover - diagnostic path
        return False, f"dependency missing: {module_name} ({exc})"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_file(path: Path) -> tuple[bool, str]:
    ok = path.exists() and path.is_file()
    return ok, f"{'found' if ok else 'missing'} file: {path}"


def check_dir_writable(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight-write-test"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        return True, f"writable directory: {path}"
    except Exception as exc:  # pragma: no cover - diagnostic path
        return False, f"directory not writable: {path} ({exc})"


def check_env_var(engine_config: dict[str, Any]) -> tuple[bool, str]:
    env_name = str(engine_config.get("openai_api_key_env", "OPENAI_API_KEY"))
    ok = bool(os.environ.get(env_name))
    return ok, f"{'found' if ok else 'missing'} env var: {env_name}"


def check_openai_network(timeout: float) -> tuple[bool, str]:
    req = request.Request("https://api.openai.com/v1/models", method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return True, f"network reachability ok: api.openai.com (status {response.status})"
    except error.HTTPError as exc:
        # 401/403 is still proof of reachability.
        if exc.code in (401, 403):
            return True, f"network reachability ok: api.openai.com (status {exc.code})"
        return False, f"network check failed: api.openai.com (status {exc.code})"
    except (error.URLError, socket.timeout) as exc:
        return False, f"network check failed: api.openai.com ({exc})"


def check_runtime_host_tools() -> list[tuple[bool, str]]:
    checks: list[tuple[bool, str]] = []
    systemctl = shutil.which("systemctl")
    if systemctl:
        checks.append((True, f"host tool available: systemctl ({systemctl})"))
    else:
        checks.append((False, "host tool missing: systemctl (runtime linux_logging collector may return unknown)"))
    return checks


def emit(results: list[tuple[bool, str]]) -> int:
    failures = [message for ok, message in results if not ok]
    for ok, message in results:
        prefix = "PASS" if ok else "FAIL"
        print(f"{prefix}: {message}")

    if failures:
        print("\nPreflight result: FAIL")
        return 1

    print("\nPreflight result: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight checks for project-iso")
    parser.add_argument("--engine-config", default="config/engine_config.json")
    parser.add_argument("--runtime-config", default="runtime/config/runtime_config.json")
    parser.add_argument("--skip-network", action="store_true", help="Skip OpenAI network reachability check")
    parser.add_argument("--network-timeout", type=float, default=8.0)
    args = parser.parse_args()

    results: list[tuple[bool, str]] = []
    results.append(check_python())
    results.append(check_dependency("jsonschema"))
    results.append(check_dependency("openpyxl"))

    engine_config_path = Path(args.engine_config)
    runtime_config_path = Path(args.runtime_config)
    results.append(check_file(engine_config_path))
    results.append(check_file(runtime_config_path))

    if engine_config_path.exists():
        engine_config = load_json(engine_config_path)
        results.append(check_env_var(engine_config))
    else:
        engine_config = {}

    prompt_files = [
        ROOT / "prompts" / "orchestrator_system.txt",
        ROOT / "prompts" / "control_planner_system.txt",
        ROOT / "prompts" / "collector_engineer_system.txt",
        ROOT / "prompts" / "evidence_engineer_system.txt",
        ROOT / "prompts" / "qa_validation_system.txt",
        ROOT / "prompts" / "security_hardening_system.txt",
        ROOT / "prompts" / "documentation_generator_system.txt",
    ]
    for prompt_file in prompt_files:
        results.append(check_file(prompt_file))

    schema_dir = ROOT / "schemas"
    runtime_output = ROOT / "runtime" / "output"
    state_dir = ROOT / "state"
    results.append(check_dir_writable(schema_dir.parent / "work_items"))
    results.append(check_dir_writable(schema_dir.parent / "work_outputs"))
    results.append(check_dir_writable(state_dir))
    results.append(check_dir_writable(runtime_output))

    if not args.skip_network:
        results.append(check_openai_network(timeout=args.network_timeout))

    results.extend(check_runtime_host_tools())

    return emit(results)


if __name__ == "__main__":
    raise SystemExit(main())
