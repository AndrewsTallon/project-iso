# Runtime bundle (offline appliance)

This directory contains deployable runtime components for the on-prem ISO/BSI appliance.

## Principles
- No AI/LLM runtime dependency.
- No outbound network requirement.
- Deterministic, schema-validated outputs.

## Layout
- `bin/`: launch scripts.
- `collectors/`: source collection scripts.
- `checks/`: deterministic control checks.
- `evidence/`: evidence hashing and manifest logic.
- `reports/`: report renderers and templates.
- `schemas/`: strict runtime JSON contracts (`additionalProperties: false`).
- `output/`: runtime-generated artifacts.
