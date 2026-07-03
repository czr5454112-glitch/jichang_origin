# G4IRSF2 High-Flow Generation Report

governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample

## Decision

Generation level is `distribution_preserving_resample` with claim scope `limited_main_claim_with_drift_audit`.
This generator does not invent new OD pairs or random pass_time/std distributions. It reuses the audited original `inputdata.txt` distribution and records drift tables.

## Manifest

Task output: `artifacts/tasks/g4irsf2_high_flow_tasks.jsonl`
Task count: `348824`
Main claim allowed: `True`

Level C remains limited: it can support fixed-map high-flow stress claims only with the drift caveat, not a paper-grade original-generator claim.
