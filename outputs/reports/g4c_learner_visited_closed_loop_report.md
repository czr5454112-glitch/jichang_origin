# G4C Learner-Visited Closed-Loop Report

Date: 2026-07-02

## Scope

This is a failure-driven learner-visited-state audit, not RL. The round1 policy remains a minimal MLP scorer with source retry and abstain/fallback heads. The verified CIE retry teacher is used only for relabeling and fallback; `edge_capacity=1` remains diagnostic-only and is not a primary constraint.

## Learner-Visited States

G4B's wrong high-confidence actions would visit `14` off-route states. G4C relabels those states with the verified CIE/A* teacher where possible and records the relabel route path for audit.

## Closed-Loop Comparison

| Policy | Planned | Node conflicts | Wrong high-conf | Fallback | Notes |
| --- | --- | --- | --- | --- | --- |
| old_edge_score_event | 97/144 | 0 |  |  | From G2/G4B baseline comparison. |
| fallback_event | 93/144 | 0 |  |  | From G2/G4B baseline comparison. |
| g4b_no_calibration | 132/144 | 0 | 14 | 0 | Existing G4B no-scenario model without failure-cluster abstain. |
| g4c_round1_no_calibration | 132/144 | 0 | 14 | 0 | Round1 relabels are included, but no cluster abstain is active. |
| g4c_round1_cluster_abstain | 144/144 | 0 | 0 | 114 | Failure-derived risky branch clusters abstain to verified CIE retry fallback. |
| cie_retry_teacher_upper_bound | 144/144 | 0 | 0 | 0 | Verified G3k CIE/Java retry teacher. |

## Abstain Calibration

| Calibration | Clusters | Fallback | Wrong high-conf | A* saved rate |
| --- | --- | --- | --- | --- |
| none_round0 | 0 | 0 | 14 | 1.000000 |
| failure_cluster_abstain_round1 | 4 | 114 | 0 | 0.903879 |

## Runtime Cost

The calibrated policy uses `114` verified fallback calls over `1186` interface decisions, saving `90.388%` of per-interface fallback calls while preserving `144/144` planned and `0` node-window conflicts.

## Next Gate

| Gate | Pass | Value | Decision |
| --- | --- | --- | --- |
| learner_visited_planned_gt_old_edgescore | True | 144>97 | g4d_candidate |
| learner_visited_planned_gt_fallback | True | 144>93 | g4d_candidate |
| learner_visited_planned_ge_138 | True | 144 | g4d_candidate |
| node_window_conflicts_zero | True | 0 | g4d_candidate |
| wrong_high_confidence_actions_decline | True | 14->0 | g4d_candidate |
| fallback_calls_reasonable | True | 0.09612142 | g4d_candidate |
| edge_capacity_primary_disabled | True | False | g4d_candidate |
| recommend_g4d_not_rl | True | G4D_candidate | g4d_candidate |

## Decision

G4C improves the failure mode from `14` wrong high-confidence actions to `0` with calibrated abstain, and raises learner-visited closed-loop accounting to `144/144`. This passes the G4C gate for G4D large-window teacher expansion. It is still not a reason to start PPO/MAPPO/RL or larger architectures.

## Artifacts

- Learner-visited state inventory: `outputs/tables/g4c_learner_visited_state_inventory.csv`
- Closed-loop comparison: `outputs/tables/g4c_closed_loop_comparison.csv`
- Abstain calibration: `outputs/tables/g4c_abstain_calibration.csv`
- Runtime cost comparison: `outputs/tables/g4c_runtime_cost_comparison.csv`
- Next gate decision: `outputs/tables/g4c_next_gate_decision.csv`
