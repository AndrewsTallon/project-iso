#!/usr/bin/env python3
"""Deterministic evidence integrity checks."""

from __future__ import annotations

from pathlib import Path

from runtime.evidence.integrity import verify_manifest_integrity


def evidence_manifest_integrity(
    run_id: str,
    manifest_path: Path,
    artifacts_root: Path,
) -> dict[str, object]:
    """Verify all manifest artifacts are present and hashes match."""
    verification = verify_manifest_integrity(manifest_path=manifest_path, artifacts_root=artifacts_root)
    return {
        "run_id": run_id,
        "check_id": "evidence_manifest_integrity",
        "control_id": "A.12.7",
        "status": "pass" if verification["ok"] else "fail",
        "severity": "high",
        "summary": verification["summary"],
        "evidence_refs": ["export_manifest", "artifact_hashes"],
    }
