#!/usr/bin/env python3
"""Deterministic Linux inventory collector."""

from __future__ import annotations

import argparse
import json
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path


def collect(run_id: str, host_id: str | None = None) -> dict[str, str]:
    resolved_host = host_id or socket.gethostname()
    return {
        "run_id": run_id,
        "collector_id": "linux_inventory",
        "host_id": resolved_host,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": resolved_host,
        "kernel": platform.release(),
        "os_pretty_name": platform.platform(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    payload = collect(run_id=args.run_id)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
