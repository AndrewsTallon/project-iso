# Runner Usage and Continuous Operations Guide

This guide is written for two audiences:

1. **Operator / tester**: runs the tool end-to-end and verifies that autonomous execution is healthy.
2. **Follow-on Codex agent**: resumes work from repository state (`state/`, `work_items/`, `work_outputs/`) with minimal human intervention.

---

## 1) What this tool does

The repository supports a deterministic compliance-delivery loop:

1. Select unblocked tasks from `architecture_plan.json`.
2. Generate task-specific `work_items/*.input.json`.
3. Produce task output JSON in `work_outputs/*.output.json`.
4. Validate output contracts and schemas.
5. Promote valid outputs into accepted task status.
6. Recompute coverage and reconcile architecture.

Primary state files used for continuous operation:

- `state/task_status.json`: lifecycle status for each task (pending, accepted, etc.).
- `state/run_history.json`: run-attempt history by task.
- `state/decision_log.jsonl`: append-only selection and reconciliation decisions.
- `state/coverage.json`: current control coverage summary.

---

## 2) One-time setup for a fresh checkout

Run these commands from repository root.

```bash
python scripts/init_state.py
python scripts/generate_next_steps.py
python scripts/generate_coverage.py
```

What to verify:

- `state/` files now exist.
- `next_steps.md` reflects current dependency ordering.
- `state/coverage.json` exists and is valid JSON.

If you intentionally need to reset state files, use:

```bash
python scripts/init_state.py --force
```

---

## 3) Operating modes

### Mode A: Manual assisted (best for debugging)

Use this mode to inspect each step and catch prompt/schema mismatches quickly.

```bash
python scripts/supervisor.py --dry-run --pick 1 --explain-selection
python scripts/agent_runner.py --task-id T01_platform_blueprint
python scripts/validate_output.py work_outputs/T01_platform_blueprint.output.json --agent control_planner
python scripts/promote_output.py --task-id T01_platform_blueprint
python scripts/generate_coverage.py
python scripts/reconcile_architecture.py --mode propose
```

### Mode B: Autonomous single-cycle

Use a single command to run one full loop for one selected task:

```bash
python scripts/engine.py --once --pick 1
```

Use `--pick N` to process multiple tasks per cycle when safe.

### Mode C: Continuous unattended operation (agents work alone)

Run the loop continuously so the system advances tasks without manual interference.

```bash
python scripts/engine.py --loop --interval-seconds 30 --pick 1
```

Recommended production-safe variant for additive architecture updates:

```bash
python scripts/engine.py --loop --interval-seconds 30 --pick 1 --auto-apply-architecture
```

Use dry run before any first unattended launch:

```bash
python scripts/engine.py --dry-run --once
```

---


### Engine model parameter policy

Model request parameters are now config-driven from `config/engine_config.json`:

- `model_params`: defaults applied to every model call (example: `temperature: 0.2`).
- `model_params_by_agent`: per-agent overrides merged on top of defaults.
- Safety guard: `scripts/engine.py` rejects resolved `temperature == 0` before any HTTP request is sent.

## Definition of Done (DoD)

This project tracks two distinct completion targets. Treat them as separate gates:

- **Development loop done**: a task execution completed correctly inside the agent-driven workflow.
- **Deployable appliance runtime done**: a production-ready offline runtime package exists for operators.

### DoD for task-level agent execution (development only)

- `work_items/<task_id>.input.json` generated deterministically.
- `work_outputs/<task_id>.envelope.json` written with run metadata/status/errors.
- `work_outputs/<task_id>.output.json` passes both:
  - `python scripts/validate_output.py ...`
  - `python scripts/contract_guard.py ...`
- promotion succeeds and task state becomes accepted in `state/task_status.json`.

### DoD for appliance runtime deliverable (product objective)

- deployable runtime exists under `runtime/` with no LLM/API dependency.
- runtime executes offline and emits evidence/check/report/export artifacts deterministically.
- packageable artifact generated under `dist/` (or equivalent) with manifest + checksums.
- operator runbook references only local scripts/binaries (no agent/model steps).

## Envelope vs Contract outputs (mandatory separation)

Never mix envelope metadata into contract outputs.

- `work_outputs/<task_id>.envelope.json` is **operational metadata only**: run status, retry attempts, errors, timing, model-call diagnostics, and task selection/provenance details.
- `work_outputs/<task_id>.output.json` is the **schema-validated business contract only**: agent-specific deliverable fields that downstream promotion consumes.
- Run-control fields (status/debug/error/attempt/timing/provenance metadata) are forbidden in `.output.json`; they must live in `.envelope.json` or under `state/`.
- `scripts/validate_output.py` and `scripts/contract_guard.py` must run only against `.output.json` targets.

| File | Role | Validation scope |
| --- | --- | --- |
| `work_outputs/<task_id>.envelope.json` | Operational metadata, non-contract | Excluded from contract validation |
| `work_outputs/<task_id>.output.json` | Business contract | Strict schema validation and promotion input |

Rule: `.output.json` must not contain extra root keys beyond the defined contract schema. Any debug/error/status content belongs in the envelope or `state/` files.

---

## 4) Suggested runbook for unattended execution

1. Initialize and baseline state.
2. Run one dry cycle.
3. Run one live cycle.
4. Start continuous loop.
5. Periodically verify health artifacts.

### Example runbook commands

```bash
python scripts/init_state.py
python scripts/generate_coverage.py
python scripts/engine.py --dry-run --once
python scripts/engine.py --once --pick 1
python scripts/engine.py --loop --interval-seconds 30 --pick 1
```

### Health checks during long-running loops

```bash
python scripts/validate_output.py work_outputs/T01_platform_blueprint.output.json --agent control_planner
python scripts/contract_guard.py work_outputs/T01_platform_blueprint.output.json
python scripts/generate_coverage.py
python scripts/supervisor.py --dry-run --pick 3 --explain-selection
```

Expected behavior:

- Validation passes for all generated output files.
- Contract guard reports no unknown root keys.
- Coverage trends upward as accepted outputs accumulate.
- Supervisor can still identify pending tasks until completion.

---

## Failure triage (deterministic)

Use this flow to classify failures quickly and choose corrective actions without mixing contract errors with operational envelope/state errors.

### Required incident bundle

Capture this bundle before making fixes so a follow-on agent can reproduce deterministically:

- Exact failing command.
- Full stdout/stderr.
- Failing file path.
- `task_id`.
- Envelope file (`work_outputs/<task_id>.envelope.json`).
- Relevant `state/decision_log.jsonl` entries.

### Stepwise triage flow

1. **Selection/preparation failures** (`scripts/supervisor.py`, `scripts/agent_runner.py`)
   - Check `state/task_status.json` for invalid lifecycle transitions and missing prerequisites.
   - Verify required task inputs/work-item artifacts exist and match selected task IDs.
2. **Contract failures** (`scripts/validate_output.py`, `scripts/contract_guard.py`)
   - Classify strictly as either:
     - **Schema mismatch** (required field/type/enum violation), or
     - **Unknown root keys** (extra non-contract keys at output root).
3. **Promotion failures** (`scripts/promote_output.py`)
   - Check `coverage_claims` presence/format requirements.
   - Check architecture update restrictions.
   - Check task-state gate failures (for example, task not eligible for promotion).
4. **Architecture reconcile failures** (`scripts/reconcile_architecture.py`)
   - Parse proposal/diff output and isolate parse or structure issues.
   - Confirm additive-change constraints are respected (no forbidden destructive edits).
5. **Runtime objective drift**
   - If a change introduces cloud/model dependency into the runtime execution path, mark as non-compliant with runtime objective and rollback/rework.

### Failure category → probable cause → corrective action

| Failure category | Probable cause | Corrective action |
| --- | --- | --- |
| Selection/preparation | Bad task-state transition, missing input artifact, stale run metadata | Repair `state/task_status.json` transition path, regenerate missing work item, rerun selection with `--explain-selection` |
| Contract (schema mismatch) | Output shape/type diverges from agent schema | Regenerate `.output.json` to match schema exactly; rerun `validate_output.py` |
| Contract (unknown root keys) | Envelope/debug/operational keys leaked into `.output.json` | Move non-contract keys into `.envelope.json`; rerun `contract_guard.py` |
| Promotion | Missing/invalid `coverage_claims`, disallowed architecture updates, task-state gate not met | Add/fix `coverage_claims`, remove restricted architecture edits, satisfy state preconditions then rerun promotion |
| Architecture reconcile | Proposal/diff parse failure or non-additive change attempt | Regenerate valid proposal/diff and constrain to additive changes only |
| Runtime objective drift | Runtime path now depends on cloud/model calls | Remove external dependency from runtime path; keep offline deterministic execution |

Interpretation rule:

- **Contract failures** are data-contract violations in `.output.json`.
- **Operational failures** are selection, envelope/state, promotion gates, and reconciliation-process issues.

---

## 5) Tester handoff workflow (for returning to Codex with issues)

When a tester finishes a run (or encounters an issue), collect and share:

1. `state/task_status.json`
2. `state/run_history.json`
3. `state/decision_log.jsonl`
4. `state/coverage.json`
5. Failing `work_outputs/*.output.json` file(s), if any
6. Exact command that produced the issue
7. Terminal output/error snippet

This package is enough for another Codex session to continue autonomously, diagnose failures, and resume progress without restarting the project.

---

## 6) Core utility commands (reference)

### Planning and work-item generation

```bash
python scripts/generate_next_steps.py
python scripts/agent_runner.py --dry-run
python scripts/agent_runner.py --task-id T01_platform_blueprint
python scripts/agent_runner.py --use-next-steps --dry-run
```

### Validation and contract enforcement

```bash
python scripts/agent_runner.py --validate work_outputs/T01_platform_blueprint.output.json --agent control_planner
python scripts/validate_output.py work_outputs/T01_platform_blueprint.output.json --agent control_planner
python scripts/contract_guard.py work_outputs/T01_platform_blueprint.output.json
python scripts/contract_guard.py tests/contracts/control_planner.valid.output.json
python scripts/contract_guard.py tests/contracts/control_planner.invalid_extra_root.output.json
# Negative example: envelope files are not contract artifacts
python scripts/validate_output.py tests/contracts/control_planner.envelope.json
```

### Promotion and reconciliation

```bash
python scripts/promote_output.py --task-id T01_platform_blueprint
python scripts/reconcile_architecture.py --mode propose
python scripts/reconcile_architecture.py --mode apply
python scripts/reconcile_architecture.py --mode propose --task-ids T01_platform_blueprint,T02_evidence_chain_design
```

### Data extraction and runtime scaffold

```bash
python scripts/extract_controls.py --excel ISO_BSI_Compliance_Automation_Map_MVP.xlsx --output data/controls.json
runtime/bin/run-once
```

---

## 7) Extending with a new agent type

When adding a new specialist agent:

1. Add schema in `schemas/` referencing `schemas/agent_envelope.schema.json` via `allOf`.
2. Add prompt in `prompts/` that enforces strict JSON-only responses and deterministic `produced_files`.
3. Register schema mapping in both:
   - `scripts/agent_runner.py`
   - `scripts/validate_output.py`
4. Ensure `architecture_plan.json` uses the exact same `assigned_agent` identifier.
5. Generate work item + sample output, then validate and guard:

```bash
python scripts/agent_runner.py --task-id <NEW_TASK_ID>
python scripts/validate_output.py work_outputs/<NEW_TASK_ID>.output.json --agent <NEW_AGENT>
python scripts/contract_guard.py work_outputs/<NEW_TASK_ID>.output.json
```
