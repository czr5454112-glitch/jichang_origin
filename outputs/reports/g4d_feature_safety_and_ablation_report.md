# G4D Feature Safety and Ablation Report

Date: 2026-07-02

## Scope

G4D adds local runtime/static features only. It does not use scenario as a model input, full CIE route suffixes, teacher next-hop, future schedules, label source, or post-hoc success.

## Forbidden Feature Audit

| Check | Pass | Decision |
| --- | --- | --- |
| scenario_not_in_model_features | True | pass |
| teacher_next_node_not_in_model_features | True | pass |
| route_path_not_in_model_features | True | pass |
| full_cie_route_suffix_not_in_model_features | True | pass |
| future_schedule_not_in_model_features | True | pass |
| future_sipp_schedule_not_in_model_features | True | pass |
| label_source_not_in_model_features | True | pass |
| post_hoc_success_not_in_model_features | True | pass |
| post_hoc_success_flag_not_in_model_features | True | pass |
| scenario_schema_metadata_only | True | pass |

## Ablation

| Ablation | All top1 | Val top1 | Test top1 |
| --- | --- | --- | --- |
| none | 0.954951 | 0.954095 | 0.958617 |
| no_enhanced_pressure | 0.954875 | 0.954095 | 0.958617 |
| no_static_topology | 0.799786 | 0.802009 | 0.810634 |
| no_historical_risk | 0.954926 | 0.954095 | 0.958617 |
| no_source_retry_pressure | 0.954951 | 0.954095 | 0.958617 |
| no_base_distance | 0.856587 | 0.856816 | 0.857255 |

## Artifacts

- Feature schema: `outputs/tables/g4d_feature_schema.csv`
- Forbidden audit: `outputs/tables/g4d_forbidden_feature_audit.csv`
- Feature ablation: `outputs/tables/g4d_feature_ablation.csv`
