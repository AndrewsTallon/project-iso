# Runtime bundle (offline appliance)

This directory contains the MVP deployable runtime for the on-prem ISO/BSI appliance.

## MVP principles
- Fully offline runtime path (no AI/LLM dependency, no outbound network requirement).
- Deterministic outputs using explicit sorting and stable rendering.
- JSON contract-first artifacts under `runtime/schemas/`.

## Runtime layout (implemented)
- `bin/`
  - `run-once`: executes one offline orchestration cycle.
  - `package-dist`: builds deterministic `dist/` packages and metadata.
- `collectors/`
  - `linux_inventory.py`: host identity / OS inventory collector.
- `checks/`
  - `check_registry.json`: declared check set.
  - `inventory_checks.py`: asset inventory control check.
  - `logging_checks.py`: local logging-service control check.
  - `evidence_integrity_checks.py`: export-manifest integrity check.
- `evidence/`
  - `hashing.py`: SHA-256 helpers.
  - `manifest.py`: deterministic manifest creation.
  - `integrity.py`: manifest verification helpers.
- `reports/`
  - `assembler.py`: report-input payload builder.
  - `renderer.py`: deterministic plaintext report renderer.
  - `templates.py`: renderer template/version constants.
- `schemas/`
  - collector/check/evidence/report/export contracts.
- `config/`
  - `runtime_config.json`: runtime settings only (no model keys).
- `orchestrator.py`
  - offline coordinator for collect → check → evidence → report → export manifest.

## Output paths
Generated run artifacts are written beneath `runtime/output/`:
- `evidence/<run_id>/normalized/`
- `checks/<run_id>/`
- `reports/<run_id>/`
- `export/<run_id>/`
- `runs/<run_id>.json`

Packaging outputs are written to repo-level `dist/`.
