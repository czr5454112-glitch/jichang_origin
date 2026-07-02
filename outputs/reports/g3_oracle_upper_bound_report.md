# G3 Oracle Upper Bound and Teacher-in-Mask Diagnosis

Date: 2026-07-02

## Scope

This diagnostic keeps the current event policy candidate set and hard shield intact, then swaps only candidate scoring for SIPP teacher-next, SIPP-rank, and K-step lookahead oracles. It is an upper-bound/route-selection diagnostic, not model training and not an RL result.

- map: `data/processed/maps/map2.json`
- tasks: `data/processed/tasks/inputdata.jsonl`
- G2 failure source: `outputs/tables/g2_failed_task_inventory.csv`
- heatmap: `outputs/figures/g3_oracle_recovery_heatmap.png` (generated)

## G2 Baseline Recap

| Family | Planned / tasks |
|---|---:|
| `rolling_horizon_sipp` | `144/144` |
| `periodic_replanning_sipp` | `144/144` |
| `edge_score_event` | `97/144` |
| `fallback_event` | `93/144` |
| `pibt_active_bag_replay` | `39/144` |

## Teacher-Next-In-Mask Audit

- audited first-divergence rows: `47`
- teacher_next_candidate_recall: `1.000`
- teacher_next_safe_recall: `0.319`

## Oracle Recovery Summary

| Oracle | Planned / 144 | Recovered EdgeScore failures | Remaining failures | New regressions | Conflicts | Recovery rate |
|---|---:|---:|---:|---:|---:|---:|
| `oracle1_teacher_next` | `97/144` | 10 | 37 | 10 | 0 | 0.213 |
| `oracle2_sipp_rank` | `77/144` | 9 | 38 | 29 | 0 | 0.191 |
| `oracle3_lookahead_k2` | `98/144` | 11 | 36 | 10 | 0 | 0.234 |
| `oracle3_lookahead_k3` | `98/144` | 11 | 36 | 10 | 0 | 0.234 |
| `oracle3_lookahead_k5` | `98/144` | 11 | 36 | 10 | 0 | 0.234 |

## Unrecoverable Decomposition

| Oracle | Context | Motif | Reason | Rows |
|---|---|---|---|---:|
| `oracle1_teacher_next` | `merge_group` | `wrong_branch_vs_sipp` | `no_safe_action_or_mask_timing` | 7 |
| `oracle2_sipp_rank` | `merge_group` | `wrong_branch_vs_sipp` | `no_safe_action_or_mask_timing` | 7 |
| `oracle2_sipp_rank` | `repair_window` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 7 |
| `oracle3_lookahead_k2` | `merge_group` | `wrong_branch_vs_sipp` | `no_safe_action_or_mask_timing` | 7 |
| `oracle3_lookahead_k3` | `merge_group` | `wrong_branch_vs_sipp` | `no_safe_action_or_mask_timing` | 7 |
| `oracle3_lookahead_k5` | `merge_group` | `wrong_branch_vs_sipp` | `no_safe_action_or_mask_timing` | 7 |
| `oracle1_teacher_next` | `repair_window` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 6 |
| `oracle3_lookahead_k2` | `repair_window` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 6 |
| `oracle3_lookahead_k3` | `repair_window` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 6 |
| `oracle3_lookahead_k5` | `repair_window` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 6 |
| `oracle1_teacher_next` | `merge_group` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 5 |
| `oracle2_sipp_rank` | `merge_group` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 5 |
| `oracle3_lookahead_k2` | `merge_group` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 5 |
| `oracle3_lookahead_k3` | `merge_group` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 5 |
| `oracle3_lookahead_k5` | `merge_group` | `hold_when_sipp_moves` | `no_safe_action_or_mask_timing` | 5 |

## Feature Need Summary

| Need | Failed rows | Teacher next safe | Oracle-1 recovered | Oracle-2 recovered | Oracle-3 K5 recovered | Still unrecovered by K5 |
|---|---:|---:|---:|---:|---:|---:|
| `mask_shield_timing` | 32 | 0 | 7 | 6 | 8 | 24 |
| `event_horizon_or_global_guidance` | 8 | 8 | 0 | 0 | 0 | 8 |
| `fault_repair_features` | 4 | 4 | 0 | 0 | 0 | 4 |
| `sipp_rank_supervision` | 3 | 3 | 3 | 3 | 3 | 0 |

## Interpretation

Development pass B: teacher next-hop is often unsafe under the current event replay mask.

Prioritize G3b mask/shield/event-horizon audit before scaling model or dataset.

The key distinction is whether failures remain after the oracle has access to the same SIPP next-hop/rank signal that a supervised EdgeRanker would learn. Recovered rows are suitable for G4 teacher-slice expansion. Unrecovered rows need mask, event-horizon, or nonlocal-context audit before larger models or RL.

## Artifacts

- Teacher-next-in-mask audit: `outputs/tables/g3_teacher_next_in_mask.csv`
- Oracle replay summary: `outputs/tables/g3_local_oracle_replay_summary.csv`
- Recovered failures: `outputs/tables/g3_oracle_recovered_failures.csv`
- Unrecoverable failures: `outputs/tables/g3_unrecoverable_failures.csv`
- Failure decomposition: `outputs/tables/g3_oracle_failure_decomposition.csv`
- Feature need summary: `outputs/tables/g3_feature_need_summary.csv`

## Gate Status

- Oracle-0 teacher-next-in-mask audit: PASS
- Oracle-1 same-step SIPP next-hop replay: PASS
- Oracle-2 SIPP-rank replay: PASS
- Oracle-3 K-step lookahead replay/diagnostic for K=2/3/5: PASS
- post-shield conflict accounting: PASS
- model training / PPO / MAPPO: not started

## Next Blocking Question

For the rows still unrecovered by `oracle3_lookahead_k5`, is the blocker an event-horizon artifact in the local replay, or does it require nonlocal reservation guidance beyond what candidate ranking can express?

## Follow-up

- Build G4 SIPP teacher slices for rows marked `sipp_rank_supervision` and `k_step_horizon_features`.
- Run G3b mask/event-horizon audit on rows marked `mask_shield_timing`, `candidate_set_or_teacher_path_alignment`, or still unrecovered by K5.
- Keep all EdgeScore/BC/DAgger language at smoke/prototype level until a closed-loop policy beats fallback and approaches SIPP on heldout diagnostics.
