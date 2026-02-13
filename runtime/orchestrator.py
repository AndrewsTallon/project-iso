#!/usr/bin/env python3
"""Deterministic offline runtime orchestrator for evidence/check/report/export."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.checks.evidence_integrity_checks import evidence_manifest_integrity
from runtime.checks.inventory_checks import asset_inventory_recorded
from runtime.checks.logging_checks import logging_service_enabled
from runtime.collectors.linux_inventory import collect
from runtime.evidence.manifest import create_export_manifest, write_manifest
from runtime.reports.assembler import build_report_input
from runtime.reports.renderer import render_plaintext


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")


def collect_linux_logging() -> dict[str, object]:
    supported = ["rsyslog", "systemd-journald"]
    active_services: list[str] = []

    diagnostics: list[str] = []
    systemctl_path = subprocess.run(["bash", "-lc", "command -v systemctl"], capture_output=True, text=True, check=False)
    collection_mode = "systemctl"

    if systemctl_path.returncode != 0 or not systemctl_path.stdout.strip():
        collection_mode = "unknown"
        diagnostics.append("systemctl not available on host")
    else:
        for service in supported:
            cmd = ["systemctl", "is-active", service]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0 and result.stdout.strip() == "active":
                active_services.append(service)
            elif result.returncode not in (0, 3, 4):
                diagnostics.append(f"systemctl is-active {service} returned {result.returncode}")

    return {
        "collector_id": "linux_logging",
        "host_id": socket.gethostname(),
        "active_services": sorted(active_services),
        "collection_mode": collection_mode,
        "diagnostics": diagnostics,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def run_once(config_path: Path) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    run_id = utc_run_id()
    output_root = Path(config["output_root"])

    evidence_normalized = output_root / "evidence" / run_id / "normalized"
    checks_dir = output_root / "checks" / run_id
    reports_dir = output_root / "reports" / run_id
    export_dir = output_root / "export" / run_id
    evidence_normalized.mkdir(parents=True, exist_ok=True)
    checks_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    inventory = collect(run_id=run_id)
    inventory_path = evidence_normalized / "linux_inventory.json"
    inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    logging_evidence = collect_linux_logging()
    logging_path = evidence_normalized / "linux_logging.json"
    logging_path.write_text(json.dumps(logging_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_path = export_dir / "export_manifest.json"
    manifest = create_export_manifest(
        bundle_version=config["bundle_version"],
        run_ids=[run_id],
        artifact_paths=[inventory_path, logging_path],
    )
    write_manifest(path=manifest_path, manifest=manifest)

    checks = [
        asset_inventory_recorded(run_id=run_id, inventory=inventory),
        logging_service_enabled(run_id=run_id, logging_evidence=logging_evidence),
        evidence_manifest_integrity(run_id=run_id, manifest_path=manifest_path, artifacts_root=Path(".")),
    ]

    check_paths: list[str] = []
    for check in checks:
        check_path = checks_dir / f"{check['check_id']}.json"
        check_path.write_text(json.dumps(check, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        check_paths.append(str(check_path))

    report_input = build_report_input(
        run_id=run_id,
        control_statuses=checks,
        evidence_index=[
            {
                "run_id": run_id,
                "collector_id": "linux_inventory",
                "host_id": inventory["host_id"],
                "timestamp_utc": inventory["timestamp_utc"],
                "command_ref": "runtime.collectors.linux_inventory.collect",
                "artifact_path": str(inventory_path),
                "artifact_hash": next(item["sha256"] for item in manifest["artifacts"] if item["path"] == str(inventory_path)),
                "control_refs": ["A.8.1"],
                "retention_class": "standard",
            },
            {
                "run_id": run_id,
                "collector_id": "linux_logging",
                "host_id": logging_evidence["host_id"],
                "timestamp_utc": logging_evidence["timestamp_utc"],
                "command_ref": "runtime.orchestrator.collect_linux_logging",
                "artifact_path": str(logging_path),
                "artifact_hash": next(item["sha256"] for item in manifest["artifacts"] if item["path"] == str(logging_path)),
                "control_refs": ["A.12.4"],
                "retention_class": "standard",
            },
        ],
    )

    report_input_path = reports_dir / "report_input.json"
    report_input_path.write_text(json.dumps(report_input, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    plaintext_report = render_plaintext(report_input)
    report_path = reports_dir / "report.txt"
    report_path.write_text(plaintext_report, encoding="utf-8")

    checkpoint = output_root / "runs" / f"{run_id}.json"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "ok",
                "evidence_files": [str(inventory_path), str(logging_path)],
                "check_files": check_paths,
                "report_files": [str(report_input_path), str(report_path)],
                "export_files": [str(manifest_path)],
            },
            indent=2,
            sort_keys=True,
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
