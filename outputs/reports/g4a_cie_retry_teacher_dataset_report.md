# G4A CIE Retry Teacher Dataset Report

Date: 2026-07-02

## Scope

G4A converts the verified G3k CIE/Java retry teacher into per-interface decision slices. It does not train a model. The primary constraints remain CIE/A* route intent, Java-style node windows, active fault edges, and Java-style unfinished-task retry. `edge_capacity=1` remains disabled as a primary constraint.

## Dataset

- G3k variant: `java_retry_tick_1s_max_delay_60s`
- Teacher routes: `144`
- Interface MOVE slices: `1186`
- Source retry slices: `17`
- Branch-node MOVE slices: `533`

## Label Distribution

| Label | Count |
| --- | --- |
| ABSTAIN_TO_SAFE_FALLBACK | 0 |
| CIE_NO_PATH_AFTER_RETRY | 0 |
| MOVE_TO_NEXT_CIE | 1186 |
| WAIT_AT_NODE_TIME_WINDOW | 0 |
| WAIT_AT_SOURCE_RETRY | 17 |

## Scenario Coverage

| Scenario | Context | Tasks | MOVE slices | Source retry |
| --- | --- | --- | --- | --- |
| legacy_first16 | no_fault | 16 | 121 | 0 |
| legacy_first16_buffer2 | buffer_capacity | 16 | 121 | 0 |
| legacy_first32 | no_fault | 32 | 252 | 1 |
| legacy_offset32_static16 | static_fault | 16 | 134 | 0 |
| legacy_offset64_merge32 | merge_window | 32 | 279 | 8 |
| legacy_offset64_repair32 | repair_window | 32 | 279 | 8 |

## Gates

| Gate | Pass | Value | Decision |
| --- | --- | --- | --- |
| teacher_replay_parity_144 | True | 144/144 | pass |
| node_window_conflicts_zero | True | 0 | pass |
| edge_capacity_primary_disabled | True | not_applied_original_cie_node_window_primary | pass |
| interface_slices_cover_all_route_edges | True | 1186 | pass |
| branch_node_slices_positive | True | 533 | pass |
| source_retry_slices_match_g3k | True | 17 | pass |
| forbidden_feature_audit_pass | True | all clear | pass |
| train_val_test_split_created | True | test;train;val | pass |
| scenario_coverage_required_contexts | True | buffer_capacity;merge_window;no_fault;repair_window;static_fault | pass |

## Leakage Guard

`teacher_next_node` is present as the supervised label but is not part of `model_input_feature_names`. Full route suffixes, future SIPP schedules, route finish times, and post-hoc success flags are not emitted as model inputs.

## Decision

G4A passes if every gate above is true. Only then may G4B train the minimal pilot scorer; this dataset is not itself a learning result.

## Artifacts

- Summary: `outputs/tables/g4a_teacher_dataset_summary.csv`
- Interface slices: `outputs/tables/g4a_interface_decision_slices.csv`
- Source retry slices: `outputs/tables/g4a_source_retry_slices.csv`
- Candidate schema: `outputs/tables/g4a_candidate_feature_schema.csv`
- Forbidden feature audit: `outputs/tables/g4a_forbidden_feature_audit.csv`
- Branch coverage: `outputs/tables/g4a_branch_node_coverage.csv`
- Scenario coverage: `outputs/tables/g4a_scenario_coverage.csv`
- Label distribution: `outputs/tables/g4a_label_distribution.csv`
- Replay parity: `outputs/tables/g4a_teacher_replay_parity.csv`
- Split: `outputs/tables/g4a_train_val_test_split.csv`
- Gate: `outputs/tables/g4a_dataset_gate.csv`
- JSONL sample: `artifacts/teacher/legacy_astar/g4a_cie_retry_junction_teacher_sample.jsonl`
