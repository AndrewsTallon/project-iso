#!/usr/bin/env python3
"""Inventory control checks."""

from __future__ import annotations


def asset_inventory_recorded(run_id: str, inventory: dict[str, str]) -> dict[str, object]:
    required = ["hostname", "kernel", "os_pretty_name"]
    missing = [key for key in required if not inventory.get(key)]
    if missing:
        return {
            "run_id": run_id,
            "check_id": "asset_inventory_recorded",
            "control_id": "A.8.1",
            "status": "fail",
            "severity": "medium",
            "summary": f"Missing required inventory fields: {', '.join(missing)}",
            "evidence_refs": ["collector_linux_inventory"],
        }

    return {
        "run_id": run_id,
        "check_id": "asset_inventory_recorded",
        "control_id": "A.8.1",
        "status": "pass",
        "severity": "medium",
        "summary": "Inventory fields are present.",
        "evidence_refs": ["collector_linux_inventory"],
    }
