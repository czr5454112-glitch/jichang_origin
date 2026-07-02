# G4B CIE Retry Policy Pilot Report

Date: 2026-07-02

## Scope

G4B trains and evaluates a minimal MLP candidate scorer from the G4A verified CIE retry interface slices. This is a pilot policy check, not a paper-grade learning result. Source retry and safety abstain remain separate heads, and `edge_capacity=1` is not used as a primary constraint.

## Shadow Replay

- Decisions: `1186`
- Disagreements: `14`
- Disagreement rate: `0.01180438`
- Abstain count: `0`
- Unsafe fault predictions: `0`

## Closed Loop

This closed loop is teacher-state route-exact replay. Only low-confidence abstain is allowed to fall back to the verified CIE retry next-hop; a wrong non-abstained prediction makes that task fail in this conservative pilot count. This is not yet a full learner-visited-state replacement for CIE/A*.

- Planned under conservative route-exact replay: `132/144`
- Model-only exact-route tasks: `132/144`
- Node-window conflicts: `0`
- Abstain fallback actions: `0`
- Non-abstained teacher disagreements: `14`
- Source retry positives: `17/17`

## Baseline Comparison

| Baseline | Role | Planned | Notes |
| --- | --- | --- | --- |
| g4b_model_only_exact_route | pilot_model_without_fallback | 132/144 | Task counted only when every interface prediction matches the teacher route. |
| g4b_with_abstain_safe_fallback | pilot_policy | 132/144 | Conservative route-exact replay; only low-confidence abstain may use verified fallback. |
| old_edge_score_event | previous_learning_baseline | 97/144 | From G2 matched active-bag diagnostics. |
| fallback_event | previous_safe_fallback_baseline | 93/144 | From G2 matched active-bag diagnostics. |
| shortest_time_to_goal_heuristic | negative_control | 0/144 | Task counted only when the heuristic matches every teacher next-hop. |
| random_safe_policy_expected | negative_control | 12.516/144 | Expected exact-route task count under uniform random outgoing choices. |
| cie_retry_teacher_upper_bound | teacher_upper_bound | 144/144 | Verified G3k CIE/Java retry teacher. |
| rolling_horizon_sipp_diagnostic_upper_bound | diagnostic_only_upper_bound | 144/144 | Diagnostic comparison only, not the teacher source. |

## Promotion Gate

| Gate | Pass | Value | Decision |
| --- | --- | --- | --- |
| offline_candidate_top1_gt_shortest_time | True | 0.98819562 > 0.85581788 | g4c_candidate |
| closed_loop_node_window_conflicts_zero | True | 0 | g4c_candidate |
| closed_loop_planned_gt_old_edgescore | True | 132>97 | g4c_candidate |
| closed_loop_planned_gt_fallback | True | 132>93 | g4c_candidate |
| closed_loop_planned_ge_120 | True | 132 | g4c_candidate |
| edge_capacity_not_primary | True | False | g4c_candidate |
| source_retry_behavior_logged | True | 17/17 | g4c_candidate |
| no_forbidden_feature_leakage | True | True | g4c_candidate |
| negative_controls_logged | True | shortest;random | g4c_candidate |
| pilot_not_paper_grade_claim | True | pilot_only | g4c_candidate |

## Decision

The conservative route-exact pilot exceeds old EdgeScore (`132` vs `97`) and fallback (`132` vs `93`) on the 144-task verified window with zero node-window conflicts. The next step may be G4C learner-visited-state data aggregation, not RL.

## Artifacts

- Offline accuracy: `outputs/tables/g4b_offline_accuracy.csv`
- Shadow replay: `outputs/tables/g4b_shadow_replay.csv`
- Closed-loop summary: `outputs/tables/g4b_closed_loop_summary.csv`
- Failure inventory: `outputs/tables/g4b_failure_inventory.csv`
- Baseline comparison: `outputs/tables/g4b_baseline_comparison.csv`
- Feature ablation: `outputs/tables/g4b_feature_ablation.csv`
- Safety abstain audit: `outputs/tables/g4b_safety_abstain_audit.csv`
- Promotion gate: `outputs/tables/g4b_promotion_gate.csv`
