#!/usr/bin/env python3
"""Build report-input payloads from check and evidence artifacts."""

from __future__ import annotations


def build_report_input(run_id: str, control_statuses: list[dict[str, object]], evidence_index: list[dict[str, object]]) -> dict[str, object]:
    return {
        "run_id": run_id,
        "control_statuses": sorted(control_statuses, key=lambda item: str(item.get("control_id", ""))),
        "evidence_index": sorted(evidence_index, key=lambda item: str(item.get("artifact_path", ""))),
    }
