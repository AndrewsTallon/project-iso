#!/usr/bin/env python3
"""Manifest creation helpers for offline exports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from runtime.evidence.hashing import sha256_file


def create_export_manifest(bundle_version: str, run_ids: list[str], artifact_paths: list[Path]) -> dict[str, object]:
    sorted_artifacts = sorted(artifact_paths, key=lambda p: str(p).replace("\\", "/"))
    return {
        "bundle_version": bundle_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_ids": sorted(run_ids),
        "artifacts": [
            {
                "path": str(path).replace("\\", "/"),
                "sha256": sha256_file(path),
            }
            for path in sorted_artifacts
        ],
    }


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
