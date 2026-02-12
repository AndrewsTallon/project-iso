#!/usr/bin/env python3
"""Generate an execution-ready next-steps document from architecture_plan.json."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path


def load_plan(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    return data["task_graph"]


def topo_levels(tasks: list[dict]) -> list[list[str]]:
    indegree: dict[str, int] = {}
    edges: dict[str, list[str]] = defaultdict(list)

    for task in tasks:
        tid = task["task_id"]
        deps = task.get("blocking_dependencies", [])
        indegree.setdefault(tid, 0)
        for dep in deps:
            edges[dep].append(tid)
            indegree[tid] = indegree.get(tid, 0) + 1
            indegree.setdefault(dep, 0)

    q = deque(sorted([tid for tid, deg in indegree.items() if deg == 0]))
    levels: list[list[str]] = []

    while q:
        level = list(q)
        levels.append(level)
        q = deque()
        for tid in level:
            for child in sorted(edges.get(tid, [])):
                indegree[child] -= 1
                if indegree[child] == 0:
                    q.append(child)

    return levels


def critical_path(tasks: list[dict]) -> list[str]:
    task_map = {t["task_id"]: t for t in tasks}
    memo: dict[str, tuple[int, list[str]]] = {}

    def longest_to(tid: str) -> tuple[int, list[str]]:
        if tid in memo:
            return memo[tid]
        deps = task_map[tid].get("blocking_dependencies", [])
        if not deps:
            memo[tid] = (1, [tid])
            return memo[tid]

        best_len = 0
        best_path: list[str] = []
        for dep in deps:
            dep_len, dep_path = longest_to(dep)
            if dep_len > best_len:
                best_len = dep_len
                best_path = dep_path

        memo[tid] = (best_len + 1, best_path + [tid])
        return memo[tid]

    best: tuple[int, list[str]] = (0, [])
    for tid in task_map:
        candidate = longest_to(tid)
        if candidate[0] > best[0]:
            best = candidate
    return best[1]


def render(tasks: list[dict]) -> str:
    task_map = {t["task_id"]: t for t in tasks}
    levels = topo_levels(tasks)
    cpath = critical_path(tasks)

    lines: list[str] = []
    lines.append("# Next Logical Steps")
    lines.append("")
    lines.append("This plan is derived from `architecture_plan.json` and focuses on immediate execution order.")
    lines.append("")

    lines.append("## Immediate next task")
    lines.append("")
    first = levels[0][0]
    t = task_map[first]
    lines.append(f"1. **{first} — {t['description']}**")
    lines.append(f"   - Assigned agent: `{t['assigned_agent']}`")
    lines.append(f"   - Expected outputs: {', '.join(t['outputs_expected'])}")
    lines.append("")

    lines.append("## Dependency waves")
    lines.append("")
    for i, wave in enumerate(levels, 1):
        lines.append(f"### Wave {i}")
        for tid in wave:
            task = task_map[tid]
            lines.append(f"- **{tid}** ({task['assigned_agent']}): {task['description']}")
        lines.append("")

    lines.append("## Critical path")
    lines.append("")
    lines.append(" -> ".join(cpath))
    lines.append("")

    lines.append("## Suggested 2-week execution checkpoint")
    lines.append("")
    lines.append("- Complete T01 (platform blueprint).")
    lines.append("- Start and complete T02 + T03 in parallel as soon as T01 closes.")
    lines.append("- Pull T04 immediately after T03, then prepare T05/T07/T08/T10 collector designs.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="architecture_plan.json")
    parser.add_argument("--output", default="next_steps.md")
    args = parser.parse_args()

    tasks = load_plan(Path(args.input))
    output = render(tasks)
    Path(args.output).write_text(output)


if __name__ == "__main__":
    main()
