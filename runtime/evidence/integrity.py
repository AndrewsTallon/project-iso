#!/usr/bin/env python3
"""Manifest integrity verification helpers."""

from __future__ import annotations

import json
from pathlib import Path

from runtime.evidence.hashing import sha256_file


def verify_manifest_integrity(manifest_path: Path, artifacts_root: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    for artifact in manifest.get("artifacts", []):
        artifact_path = artifacts_root / artifact["path"]
        if not artifact_path.exists():
            failures.append(f"missing:{artifact['path']}")
            continue
        actual = sha256_file(artifact_path)
        if actual.lower() != artifact["sha256"].lower():
            failures.append(f"hash_mismatch:{artifact['path']}")

    if failures:
        return {"ok": False, "summary": f"Integrity failures: {', '.join(failures)}"}
    return {"ok": True, "summary": "All referenced artifacts exist and hashes match."}
