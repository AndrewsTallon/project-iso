#!/usr/bin/env python3
"""Deterministic text renderer for offline reports."""

from __future__ import annotations


def render_plaintext(report_input: dict[str, object]) -> str:
    run_id = report_input["run_id"]
    statuses = report_input.get("control_statuses", [])

    lines = [f"Runtime compliance report: {run_id}", ""]
    for status in statuses:
        lines.append(
            " - {control_id}: {status} ({summary})".format(
                control_id=status.get("control_id", "unknown"),
                status=status.get("status", "unknown"),
                summary=status.get("summary", ""),
            )
        )
    return "\n".join(lines) + "\n"
