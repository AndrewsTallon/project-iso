# project-iso

This repository captures an ISO/BSI compliance automation architecture and execution plan.

## Contents

- `architecture_plan.json`: machine-readable architecture summary, phased plan, and task dependency graph.
- `ISO_BSI_Compliance_Automation_Map_MVP.xlsx`: original source mapping workbook.
- `scripts/generate_next_steps.py`: utility to derive a dependency-ordered execution brief.
- `next_steps.md`: generated "what to do next" plan from the task graph.

## Regenerating next steps

```bash
python scripts/generate_next_steps.py
```
