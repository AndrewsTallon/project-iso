# Next Logical Steps

This plan is derived from `architecture_plan.json` and focuses on immediate execution order.

## Immediate next task

1. **T01_platform_blueprint — Define appliance-wide architecture constraints, storage limits, retention tiers, and trust boundaries for Linux on Intel N100.**
   - Assigned agent: `control_planner`
   - Expected outputs: Architecture constraint specification, module interface contract v1

## Dependency waves

### Wave 1
- **T01_platform_blueprint** (control_planner): Define appliance-wide architecture constraints, storage limits, retention tiers, and trust boundaries for Linux on Intel N100.

### Wave 2
- **T02_evidence_chain_design** (evidence_engineer): Design canonical evidence manifest, hash/sign strategy, timestamp workflow, append-only storage, and export package format.
- **T03_shared_connector_framework** (collector_engineer): Design reusable agentless connector framework for SSH/WinRM/SNMP/API with credential vault integration and throttled scheduling.

### Wave 3
- **T12_security_hardening_baseline** (security_hardening): Define appliance hardening baseline for key management, local service isolation, and secure storage on Linux host.
- **T04_asset_inventory_model** (control_planner): Design normalized asset schema and reconciliation logic for hosts, software, services, owners, and business tags.

### Wave 4
- **T05_identity_access_collectors** (collector_engineer): Design identity and privileged-access evidence collectors and account entitlement correlation approach.
- **T06_config_change_baseline_design** (control_planner): Design baseline/drift model, approved-change linkage, and audit-testing protection evidence flow.
- **T07_vuln_malware_pipeline_design** (collector_engineer): Design ingestion and scoring pipeline for malware and vulnerability posture from existing on-prem tools and OS-native sources.
- **T08_logging_monitoring_time_design** (collector_engineer): Design log source onboarding, monitoring status checks, and time-sync verification model for incident evidence timelines.
- **T09_backup_resilience_design** (control_planner): Design backup job/retention/restore-test evidence model and resilience readiness checks.
- **T10_network_crypto_design** (collector_engineer): Design network state collectors for topology, service exposure, segmentation, and cryptographic posture evidence.

### Wave 5
- **T11_evidence_binding_for_collectors** (evidence_engineer): Define evidence envelope bindings so all collector outputs are hashed, signed, timestamped, and traceable to control IDs.

### Wave 6
- **T13_mvp_validation_plan** (qa_validation): Design MVP control validation matrix and acceptance criteria for evidence completeness, freshness, and integrity.

### Wave 7
- **T14_mvp_documentation_pack** (documentation_generator): Design documentation artifacts for auditors: architecture dossier, control mapping catalog, evidence export operation guide.

### Wave 8
- **T15_data_lifecycle_v2_design** (control_planner): Design v2 data deletion, masking, leakage, and test-data evidence model linked to legal and privacy obligations.
- **T16_secure_dev_v2_design** (collector_engineer): Design v2 secure-development evidence ingestion from on-prem repositories and CI/test systems.

### Wave 9
- **T17_v2_evidence_extension** (evidence_engineer): Extend evidence chain mappings and export manifests for v2 modules while preserving backward compatibility.

### Wave 10
- **T18_v2_validation_and_docs** (qa_validation): Define v2 QA validation plan and auditor documentation for extended technical control set.

### Wave 11
- **T19_governance_v3_design** (control_planner): Design governance/personnel/physical/supplier evidence workflows and review cadences leveraging established evidence integrity framework.

### Wave 12
- **T20_v3_validation_docs_hardening** (documentation_generator): Finalize v3 validation strategy, documentation set, and hardening updates for long-term on-prem operations.

## Critical path

T01_platform_blueprint -> T03_shared_connector_framework -> T04_asset_inventory_model -> T05_identity_access_collectors -> T11_evidence_binding_for_collectors -> T13_mvp_validation_plan -> T14_mvp_documentation_pack -> T15_data_lifecycle_v2_design -> T17_v2_evidence_extension -> T18_v2_validation_and_docs -> T19_governance_v3_design -> T20_v3_validation_docs_hardening

## Suggested 2-week execution checkpoint

- Complete T01 (platform blueprint).
- Start and complete T02 + T03 in parallel as soon as T01 closes.
- Pull T04 immediately after T03, then prepare T05/T07/T08/T10 collector designs.
