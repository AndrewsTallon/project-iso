# Runner Usage

## Generate next steps

- Use the existing planner utility to refresh execution sequencing from `architecture_plan.json`.

```bash
python scripts/generate_next_steps.py
```

## Produce work items for tasks

- Build work items for currently unblocked tasks.

```bash
python scripts/agent_runner.py --dry-run
```

- Build a specific task work item and create placeholder output file.

```bash
python scripts/agent_runner.py --task-id T01_platform_blueprint
```

- Select tasks listed in `next_steps.md` instead of using dependency checks.

```bash
python scripts/agent_runner.py --use-next-steps --dry-run
```

## Extract control data from Excel

- Convert the workbook into JSON for offline inspection and downstream tooling.

```bash
python scripts/extract_controls.py --excel ISO_BSI_Compliance_Automation_Map_MVP.xlsx --output data/controls.json
```

## Validate an agent output

- Validate from the main runner.

```bash
python scripts/agent_runner.py --validate work_outputs/T01_platform_blueprint.output.json --agent control_planner
```

- Validate with the standalone utility.

```bash
python scripts/validate_output.py work_outputs/T01_platform_blueprint.output.json --agent control_planner
```

## Add a new agent type

- Add a new schema under `schemas/` that references `schemas/agent_envelope.schema.json` via `allOf`.
- Add a new system prompt under `prompts/` that requires strict JSON only output and includes deterministic `produced_files` paths.
- Register the agent to schema mapping in both `scripts/agent_runner.py` and `scripts/validate_output.py`.
- Ensure task graph entries in `architecture_plan.json` use the same `assigned_agent` string.
- Generate new work items and validate a sample output.


## Run the autonomous engine

- Single full cycle (task selection -> model output -> validation -> promotion -> coverage -> reconciliation propose):

```bash
python scripts/engine.py --once --pick 1
```

- Continuous loop mode:

```bash
python scripts/engine.py --loop --interval-seconds 30 --pick 1
```

- Dry run (no model/API calls):

```bash
python scripts/engine.py --dry-run --once
```

- Optional guarded auto-apply for architecture reconciliation:

```bash
python scripts/engine.py --once --auto-apply-architecture
```

## Enforce strict root contracts

- Reject JSON outputs that include unknown root keys.

```bash
python scripts/contract_guard.py work_outputs/
```

- Run contract guard fixtures:

```bash
python scripts/contract_guard.py tests/contracts/control_planner.valid.json
python scripts/contract_guard.py tests/contracts/control_planner.invalid_extra_root.json
```

## Validate output directories recursively

```bash
python scripts/validate_output.py work_outputs/ --recursive
```

## Runtime scaffold smoke execution

```bash
runtime/bin/run-once
```
