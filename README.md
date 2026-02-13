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


## Environment prerequisites

- Python 3.10+
- Install dependencies:

```bash
pip install -r requirements.txt
```

- Run a preflight check before first execution:

```bash
python scripts/preflight.py
```

For runtime-only (on-prem appliance) deployment, run the runtime package without agents/model calls:

```bash
runtime/bin/run-once
```

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

Bundled sample outputs for `T01`–`T04` are provided in `work_outputs/` and include deterministic `coverage_claims` derived from each task work item so promotion commands can be run directly.

- Guard root-level output contracts (reject unknown keys, including extra root keys):

```bash
python scripts/contract_guard.py work_outputs/
```

- Validate all outputs recursively:

```bash
python scripts/validate_output.py work_outputs/ --recursive
```

- Negative example (operational envelope is not a contract artifact):

```bash
python scripts/validate_output.py tests/contracts/control_planner.envelope.json
```

- Run minimal offline runtime orchestrator once:

```bash
runtime/bin/run-once
```


## Self-expanding loop

Run the persistent loop in this order:

`python scripts/supervisor.py --dry-run ...` is non-mutating: it evaluates and prints selections but does not advance task state or write `state/task_status.json`, `state/run_history.json`, or `state/decision_log.jsonl`.

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
python scripts/supervisor.py --dry-run --pick 2  # non-mutating preview
python scripts/supervisor.py --pick 1 --update-coverage
python scripts/validate_output.py work_outputs/T01_platform_blueprint.output.json --agent control_planner
python scripts/promote_output.py --task-id T01_platform_blueprint
python scripts/promote_output.py --task-id T02_evidence_chain_design
python scripts/promote_output.py --task-id T03_shared_connector_framework
python scripts/promote_output.py --task-id T04_asset_inventory_model
python scripts/generate_coverage.py
# Precondition: reconcile only promoted tasks (accepted/validated in state/task_status.json)
python scripts/reconcile_architecture.py --mode propose
```


## Architecture reconciliation

Use the conservative reconciler to derive architecture proposals from accepted or validated task outputs.

Precondition: tasks must already be promoted (state is `accepted` or `validated` in `state/task_status.json`).
If reconciliation reports effectively empty sources (for example, `sources=0` with no changes), there were no eligible promoted tasks.
Fix by running promotion/state update first (for example, `python scripts/promote_output.py --task-id <TASK_ID>`), then rerun reconciliation.

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
