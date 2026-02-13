#!/usr/bin/env python3
"""Deterministic logging-related control checks."""

from __future__ import annotations


def logging_service_enabled(run_id: str, logging_evidence: dict[str, object]) -> dict[str, object]:
    """Pass when at least one supported logging service is active."""
    active_services = logging_evidence.get("active_services", [])
    has_active = isinstance(active_services, list) and len(active_services) > 0
    collection_mode = logging_evidence.get("collection_mode", "systemctl")

    if collection_mode == "unknown":
        return {
            "run_id": run_id,
            "check_id": "logging_service_enabled",
            "control_id": "A.12.4",
            "status": "warn",
            "severity": "medium",
            "summary": "Logging service state could not be determined on this host.",
            "evidence_refs": ["collector_linux_logging"],
        }

    return {
        "run_id": run_id,
        "check_id": "logging_service_enabled",
        "control_id": "A.12.4",
        "status": "pass" if has_active else "fail",
        "severity": "high",
        "summary": (
            "At least one supported logging service is active."
            if has_active
            else "No supported logging service detected as active."
        ),
        "evidence_refs": ["collector_linux_logging"],
    }
