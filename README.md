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

- `scripts/contract_guard.py`: root-key contract guard to fail outputs containing unknown keys.
- `runtime/`: deployable offline runtime scaffolding (collectors, checks, schemas, orchestrator).
- `data/control_map/control_to_check_map.json`: initial ISO/BSI to executable check mapping for MVP.


- `scripts/engine.py`: autonomous single-command loop runner for selection, model execution, validation, promotion, coverage refresh, and architecture reconciliation.
- `config/engine_config.json`: model mapping, model parameter defaults/overrides, and API key env-var name for the engine.
- `scripts/extract_controls.py`: workbook-to-JSON extractor utility.
- `data/`: extracted control datasets.
- `work_items/`: deterministic input payloads for agent tasks.
- `work_outputs/`: task outputs (`<task_id>.output.json`), operational envelopes (`<task_id>.envelope.json`), and deterministic artifacts (`<task_id>.artifacts/`).
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

Only `*.output.json` files are discoverable by contract validation and promotion gates; `*.envelope.json` files are operational metadata and are intentionally ignored by those tools.

- Guard root-level output contracts (reject unknown keys, including extra root keys):

```bash
python scripts/contract_guard.py work_outputs/
```

- Validate all outputs recursively:

```bash
python scripts/validate_output.py work_outputs/ --recursive
```

- Run minimal offline runtime orchestrator once:

```bash
runtime/bin/run-once
```


## Self-expanding loop

Run the persistent loop in this order:

1. Initialize state files.
2. Compute baseline coverage.
3. Let the supervisor pick unblocked tasks and generate `work_items/` using `scripts/agent_runner.py`.
4. Run agents and produce `work_outputs/*.output.json`.
5. Validate outputs against schemas.
6. Promote produced outputs to accepted with deterministic gates.
7. Recompute coverage.

Example commands:

```bash
python scripts/init_state.py
python scripts/generate_coverage.py
python scripts/supervisor.py --dry-run --pick 2
python scripts/supervisor.py --pick 1 --update-coverage
python scripts/validate_output.py work_outputs/T01_platform_blueprint.output.json --agent control_planner
python scripts/promote_output.py --task-id T01_platform_blueprint
python scripts/generate_coverage.py
```


## Architecture reconciliation

Use the conservative reconciler to derive architecture proposals from accepted or validated task outputs.

```bash
python scripts/reconcile_architecture.py --mode propose
```

Apply mode archives the previous plan under `architecture/versions/` before writing the updated `architecture_plan.json`.

```bash
python scripts/reconcile_architecture.py --mode apply
```

Optional filters and paths:

```bash
python scripts/reconcile_architecture.py --mode propose --task-ids T01_platform_blueprint,T02_evidence_chain_design
python scripts/reconcile_architecture.py --work-outputs work_outputs/ --task-status state/task_status.json
```


## Autonomous engine

Run one complete cycle for one picked task (default):

```bash
python scripts/engine.py --once --pick 1
```

Run continuously:

```bash
python scripts/engine.py --loop --interval-seconds 30 --pick 1
```

Dry run mode (no model calls):

```bash
python scripts/engine.py --dry-run --once
```

Enable guarded auto-apply for small additive architecture diffs:

```bash
python scripts/engine.py --once --auto-apply-architecture
```


Engine calls merge `model_params` + `model_params_by_agent` from config. Temperature must be non-zero if provided; `temperature=0` is explicitly rejected.
