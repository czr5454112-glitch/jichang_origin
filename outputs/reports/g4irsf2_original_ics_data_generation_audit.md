# G4IRSF2 Original ICS Data Generation Audit

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `dafc6e0`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
original_ics_project_access: FOUND
ics_origin_root: `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目`

## Finding

The original ICS project is accessible and contains the Java simulation code plus `inputdata.txt` and `map2.txt`.
The audited Java code releases tasks from the existing `inputdata.txt` source queues at each epoch; the random OD generator code is commented out.
No active original-project generator was found for creating new large-scale flight/OD/pass_time distributions. Therefore G4IRSF2 uses `distribution_preserving_resample` with drift audit, not Level A/B.

## Rule Status

| Status | Count |
| --- | --- |
| FOUND | 20 |
| INFERRED_FROM_DATA | 1 |
| MISSING | 1 |

## Evidence Tables

- `outputs/tables/g4irsf2_original_ics_file_inventory.csv` rows: 341
- `outputs/tables/g4irsf2_original_ics_rule_inventory.csv`
- `outputs/tables/g4irsf2_original_ics_flow_generation_evidence.csv`
- `outputs/tables/g4irsf2_original_ics_baseline_rule_evidence.csv`

Negative result retained: original-project-generated and original-rule-replay high-flow streams are not claimed in this run.
