# project-iso

This repository captures an ISO 27001 + BSI IT-Grundschutz compliance automation architecture and execution scaffold for an on-prem appliance.

## Contents

- `architecture_plan.json`: machine-readable architecture summary, phased plan, and task dependency graph.
- `ISO_BSI_Compliance_Automation_Map_MVP.xlsx`: source mapping workbook.
- `scripts/generate_next_steps.py`: utility to derive a dependency-ordered execution brief.
- `next_steps.md`: generated "what to do next" plan from the task graph.
- `schemas/`: strict JSON schemas for each agent output contract.
- `prompts/`: system prompts for orchestrator and specialist agents.
- `scripts/agent_runner.py`: scaffold runner for work-item generation and schema validation.
- `scripts/validate_output.py`: standalone output validator.
- `scripts/extract_controls.py`: workbook-to-JSON extractor utility.
- `data/`: extracted control datasets.
- `work_items/`: deterministic input payloads for agent tasks.
- `work_outputs/`: deterministic expected output files per task.
- `modules/`: future collector module outputs.
- `docs/runner_usage.md`: operational usage guide.

## Workflow

- Regenerate dependency-oriented execution guidance.

```bash
python scripts/generate_next_steps.py
```

- Build task work items from `architecture_plan.json` and the Excel control mapping.

```bash
python scripts/agent_runner.py --dry-run
```

- Validate strict JSON output against the assigned agent schema.

```bash
python scripts/validate_output.py work_outputs/T01_platform_blueprint.output.json --agent control_planner
```

- Extract all workbook rows into JSON for offline indexing.

```bash
python scripts/extract_controls.py --output data/controls.json
```

For detailed commands and extension guidance, see `docs/runner_usage.md`.
