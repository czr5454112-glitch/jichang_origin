# G3d Legacy-A* Teacher Wait/Horizon Audit

Date: 2026-07-02

## 1. Scope and non-claim boundary

This audit explains blocked Legacy-A* route-next labels from G3c by replaying wait, jump-to-safe-time, reroute, diagnostic ablation, and hybrid repair variants. It does not train a model, does not start RL/PPO/MAPPO, does not create a large G4A dataset, and does not modify legacy Java.

- map: `data/processed/maps/map2.json`
- tasks: `data/processed/tasks/inputdata.jsonl`
- teacher source: `python_faithful_legacy_astar_wait_horizon_audit`

## 2. G3c recap

| Metric | Value |
| --- | --- |
| G3c planned | 78/144 |
| G3c blocked/unavailable slices | 614 |
| G3c candidate recall | 1.000 |
| G3c safe recall | 0.610 |
| G3 SIPP safe recall | 0.319 |
| G3c post-shield conflicts | 0 |

## 3. Blocked slice root-cause ledger

G3d baseline reproduction records `614` non-MOVE_NOW slices. The dominant reasons remain edge-capacity timing and Legacy no-path cases; merge scenarios add merge-group coupling.

| Reason | Rows |
| --- | --- |
| edge_capacity | 506 |
| legacy_astar_no_path | 42 |
| edge_capacity+merge_group | 35 |
| merge_group | 31 |

## 4. Earliest-safe-time / wait-until-safe audit

Earliest-safe rows written: `572`. Fixed-hold sweeps test 1s/2s/5s event-horizon effects; jump-to-earliest-safe-time separates transient waits from true no-path or unsafe labels.

## 5. Replay variants and planned-count comparison

| Variant | Planned | Primary coverage | Branch coverage | Conflicts | Real conflicts |
| --- | --- | --- | --- | --- | --- |
| ablation_disable_edge_capacity | 125/144 | 0.872 | 1.000 | 0 | 491 |
| ablation_disable_merge_group | 78/144 | 0.599 | 0.469 | 0 | 0 |
| ablation_edge_capacity_2 | 96/144 | 0.775 | 0.780 | 0 | 131 |
| g3c_baseline_reproduction | 78/144 | 0.593 | 0.487 | 0 | 0 |
| hybrid_legacy_wait_sipp_fallback | 92/144 | 0.808 | 0.958 | 0 | 0 |
| jump_to_earliest_safe_time | 88/144 | 0.800 | 0.932 | 0 | 0 |
| reroute_from_current_legacy | 94/144 | 0.683 | 0.642 | 0 | 0 |
| wait_fixed_hold_1s | 78/144 | 0.928 | 0.948 | 0 | 0 |
| wait_fixed_hold_2s | 80/144 | 0.920 | 0.940 | 0 | 0 |
| wait_fixed_hold_5s | 93/144 | 0.881 | 0.969 | 0 | 0 |

Best primary wait/reroute variant: `reroute_from_current_legacy` with `94/144` planned, `0.642` branch coverage, and `0` post-shield conflicts.
Hybrid repair reaches `92/144`, but its SIPP/fallback labels are auxiliary repair data, not primary Legacy labels.
Capacity diagnostic rows show edge-capacity sensitivity: edge_capacity=2 plans `96/144`; disabling edge capacity plans `125/144` but has `491` real-constraint conflicts, so it is diagnosis only.

## 6. Reroute-from-current audit

Reroute audit rows written: `121`. Reroute labels are only primary G4A candidates when the alternate Legacy-compatible next-hop is safe under the current hard mask.

## 7. Branch vs linear decision breakdown

| Variant | Scenario | Node kind | Coverage | Primary labels |
| --- | --- | --- | --- | --- |
| g3c_baseline_reproduction | legacy_offset64_merge32 | branch | 0.463 | 56 |
| g3c_baseline_reproduction | legacy_offset64_merge32 | linear | 0.537 | 108 |
| wait_fixed_hold_1s | legacy_offset64_merge32 | branch | 0.934 | 113 |
| wait_fixed_hold_1s | legacy_offset64_merge32 | linear | 0.836 | 168 |
| wait_fixed_hold_2s | legacy_offset64_merge32 | branch | 0.932 | 96 |
| wait_fixed_hold_2s | legacy_offset64_merge32 | linear | 0.819 | 136 |
| wait_fixed_hold_5s | legacy_offset64_merge32 | branch | 0.981 | 102 |
| wait_fixed_hold_5s | legacy_offset64_merge32 | linear | 0.726 | 138 |
| jump_to_earliest_safe_time | legacy_offset64_merge32 | branch | 0.904 | 66 |
| jump_to_earliest_safe_time | legacy_offset64_merge32 | linear | 0.570 | 106 |
| reroute_from_current_legacy | legacy_offset64_merge32 | branch | 0.559 | 76 |
| reroute_from_current_legacy | legacy_offset64_merge32 | linear | 0.567 | 115 |
| ablation_edge_capacity_2 | legacy_offset64_merge32 | branch | 0.758 | 69 |
| ablation_edge_capacity_2 | legacy_offset64_merge32 | linear | 0.500 | 112 |
| ablation_disable_edge_capacity | legacy_offset64_merge32 | branch | 1.000 | 73 |
| ablation_disable_edge_capacity | legacy_offset64_merge32 | linear | 0.491 | 109 |
| ablation_disable_merge_group | legacy_offset64_merge32 | branch | 0.378 | 56 |
| ablation_disable_merge_group | legacy_offset64_merge32 | linear | 0.674 | 120 |
| hybrid_legacy_wait_sipp_fallback | legacy_offset64_merge32 | branch | 0.961 | 74 |
| hybrid_legacy_wait_sipp_fallback | legacy_offset64_merge32 | linear | 0.575 | 107 |

## 8. Label taxonomy for G4A

G4A primary-eligible manifest rows: `5706` across non-diagnostic primary variants. Primary labels are restricted to `MOVE_NOW_LEGACY`, `HOLD_UNTIL_SAFE_LEGACY_NEXT`, and `REROUTE_NOW_LEGACY`; `LEGACY_NO_PATH`, `FALLBACK_SAFE_MOVE`, `SIPP_REPAIR_MOVE`, and `ABSTAIN_NO_TEACHER` remain auxiliary/exclusion labels.

| Taxonomy | Rows |
| --- | --- |
| MOVE_NOW_LEGACY | 1024 |
| LEGACY_NEXT_TEMPORARILY_BLOCKED | 372 |
| ABSTAIN_NO_TEACHER | 50 |
| LEGACY_NO_PATH | 37 |
| REROUTE_NOW_LEGACY | 34 |
| LEGACY_NEXT_GLOBALLY_UNSAFE | 32 |

## 9. Decision: enter G4A, run more G3d, or fix event semantics first

Diagnostic pass: do not enter broad G4A or training yet. Wait/reroute semantics improve label taxonomy, but planned count or branch effective coverage remains below the G3d gate. Continue with event-horizon, edge-capacity timing, and no-path semantics repair.

## Artifacts

- Blocked ledger: `outputs/tables/g3d_blocked_slice_ledger.csv`
- Earliest safe labels: `outputs/tables/g3d_earliest_safe_time_labels.csv`
- Replay variant summary: `outputs/tables/g3d_teacher_replay_variant_summary.csv`
- Recovered tasks: `outputs/tables/g3d_wait_until_safe_recovered_tasks.csv`
- Still blocked after wait: `outputs/tables/g3d_still_blocked_after_wait.csv`
- Reroute audit: `outputs/tables/g3d_legacy_reroute_from_current.csv`
- Branch vs linear recall: `outputs/tables/g3d_branch_vs_linear_recall.csv`
- Edge-capacity hotspots: `outputs/tables/g3d_edge_capacity_hotspots.csv`
- Label taxonomy: `outputs/tables/g3d_teacher_label_taxonomy.csv`
- G4A eligible manifest: `outputs/tables/g3d_g4a_eligible_slice_manifest.csv`
- Wait-label JSONL sample: `artifacts/teacher/legacy_astar/g3d_legacy_astar_wait_labels_sample.jsonl`
- Block reason heatmap: `outputs/figures/g3d_block_reason_heatmap.png`
