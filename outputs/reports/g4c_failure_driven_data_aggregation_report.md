# G4C Failure-Driven Data Aggregation Report

Date: 2026-07-02

## Scope

G4C does not use RL, GNN, or Transformer models. It audits the G4B failures, keeps `scenario` as metadata only, relabels learner-visited offset states with the verified CIE/A* teacher, and writes a calibrated minimal round1 policy artifact. `edge_capacity=1` remains disabled as a primary constraint.

## Feature Hygiene

| Check | Pass | Value |
| --- | --- | --- |
| scenario_schema_metadata_only | True | False |
| scenario_not_in_model_features | True | ['candidate_faulted', 'candidate_is_goal', 'candidate_node_pressure_scaled', 'candidate_node_type_scaled', 'candidate_service_time_scaled', 'candidate_shortest_time_to_goal_scaled', 'candidate_travel_time_scaled', 'current_node_scaled', 'goal_node_scaled', 'is_branch_node', 'local_node_pressure_scaled', 'out_degree_scaled', 'time_slack_scaled'] |
| teacher_next_not_in_model_features | True | ['candidate_faulted', 'candidate_is_goal', 'candidate_node_pressure_scaled', 'candidate_node_type_scaled', 'candidate_service_time_scaled', 'candidate_shortest_time_to_goal_scaled', 'candidate_travel_time_scaled', 'current_node_scaled', 'goal_node_scaled', 'is_branch_node', 'local_node_pressure_scaled', 'out_degree_scaled', 'time_slack_scaled'] |
| full_route_suffix_not_in_model_features | True | ['candidate_faulted', 'candidate_is_goal', 'candidate_node_pressure_scaled', 'candidate_node_type_scaled', 'candidate_service_time_scaled', 'candidate_shortest_time_to_goal_scaled', 'candidate_travel_time_scaled', 'current_node_scaled', 'goal_node_scaled', 'is_branch_node', 'local_node_pressure_scaled', 'out_degree_scaled', 'time_slack_scaled'] |
| future_schedule_not_in_model_features | True | ['candidate_faulted', 'candidate_is_goal', 'candidate_node_pressure_scaled', 'candidate_node_type_scaled', 'candidate_service_time_scaled', 'candidate_shortest_time_to_goal_scaled', 'candidate_travel_time_scaled', 'current_node_scaled', 'goal_node_scaled', 'is_branch_node', 'local_node_pressure_scaled', 'out_degree_scaled', 'time_slack_scaled'] |
| label_source_not_in_model_features | True | ['candidate_faulted', 'candidate_is_goal', 'candidate_node_pressure_scaled', 'candidate_node_type_scaled', 'candidate_service_time_scaled', 'candidate_shortest_time_to_goal_scaled', 'candidate_travel_time_scaled', 'current_node_scaled', 'goal_node_scaled', 'is_branch_node', 'local_node_pressure_scaled', 'out_degree_scaled', 'time_slack_scaled'] |
| post_hoc_success_not_in_model_features | True | ['candidate_faulted', 'candidate_is_goal', 'candidate_node_pressure_scaled', 'candidate_node_type_scaled', 'candidate_service_time_scaled', 'candidate_shortest_time_to_goal_scaled', 'candidate_travel_time_scaled', 'current_node_scaled', 'goal_node_scaled', 'is_branch_node', 'local_node_pressure_scaled', 'out_degree_scaled', 'time_slack_scaled'] |
| no_scenario_top1_not_collapsed | True | 0.9881956155143339 |
| no_scenario_beats_shortest_time | True | 0.98819562>0.85581788 |
| scenario_lookup_diagnostic_recorded | True | 0.98313659 |

## Failure Clusters

| Current | Teacher | Predicted | Candidates | Count | Interpretation |
| --- | --- | --- | --- | --- | --- |
| 6 | 8 | 12 | [8, 12] | 2 | CIE chooses 6->8 in a rare branch while scorer prefers 6->12; this is a high-risk two-way split. |
| 11 | 14 | 13 | [13, 14] | 7 | CIE branch preference at 11 alternates between 13 and 14; local features underrepresent path-order/tie semantics. |
| 16 | 21 | 17 | [17, 21] | 3 | CIE sometimes prefers the longer-looking 16->21 branch; local shortest-time bias picks 16->17. |
| 19 | 25 | 18 | [18, 25] | 2 | CIE sometimes sends bags via 19->25 rather than 19->18; this is a route-shape preference not captured by simple distance. |

## Relabeling

- Relabelled rows: `28`
- MOVE labels: `28`
- Abstain labels: `0`
- Calibrated abstain clusters: `4`

## Round1 Summary

| Iteration | Offline top1 | Route-exact planned | Wrong high-conf | Fallback |
| --- | --- | --- | --- | --- |
| round0_g4b_no_scenario | 0.98819562 | 132 | 14 | 0 |
| round1_dagger_relabel_no_calibration | 0.98819562 | 132 | 14 | 0 |
| round1_dagger_with_cluster_abstain | 0.98819562 | 144 | 0 | 114 |

## Decision

Round1 with failure-cluster abstain reaches `144/144` in route-exact accounting and reduces wrong high-confidence actions to `0`. The separate learner-visited closed-loop gate is written by `run_g4c_learner_visited_closed_loop.py`.

## Artifacts

- Feature audit: `outputs/tables/g4c_no_scenario_feature_audit.csv`
- Failure clusters: `outputs/tables/g4c_failure_cluster_summary.csv`
- Relabelled slices: `outputs/tables/g4c_relabelled_failure_slices.csv`
- DAgger summary: `outputs/tables/g4c_dagger_iteration_summary.csv`
- Teacher sample: `artifacts/teacher/legacy_astar/g4c_dagger_round1_teacher_sample.jsonl`
- Round1 model: `artifacts/models/g4c_minimal_policy_round1.json`
