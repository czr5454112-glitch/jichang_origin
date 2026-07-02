# G2 Learning Gap Autopsy

Date: 2026-07-02

## Scope

This diagnostic explains why the current learned/prototype routing families lose to the strong SIPP baselines on the Phase9 matched real `map2/inputdata` windows. It is a failure-driven research artifact, not a new learning-success claim.

- map: `data/processed/maps/map2.json`
- tasks: `data/processed/tasks/inputdata.jsonl`
- runtime model: `artifacts/runtime/phase8_edge_score_runtime_model.txt`
- heatmap: `outputs/figures/g2_failure_heatmap.png` (generated)

## Matched Planned Counts

| Family | Planned / tasks | Interpretation |
|---|---:|---|
| `rolling_horizon_sipp` | `144/144` | teacher/reference for first-divergence diagnosis |
| `periodic_replanning_sipp` | `144/144` | strong active-bag replanning baseline |
| `edge_score_event` | `97/144` | learned smoke/prototype runtime policy |
| `fallback_event` | `93/144` | shortest-safe event fallback |
| `pibt_active_bag_replay` | `39/144` | local active-bag resolver stress baseline |

## Failure Inventory

- EdgeScore failures against rolling-horizon SIPP: `47` task-scenario rows.
- Fallback failures against rolling-horizon SIPP: `51` task-scenario rows.
- PIBT active-bag replay failures against rolling-horizon SIPP: `105` task-scenario rows.
- Top first-divergence nodes across failed rows: `4:28, 16:24, 18:23, 6:22, 28:16, 22:13, 19:12, 11:10, 23:9, 7:9`.

## Top Failure Motifs

| Policy | Motif | Context | Failed tasks | Share |
|---|---|---|---:|---:|
| `pibt_active_bag_replay` | `wrong_branch_vs_sipp` | `no_fault` | 22 | 0.210 |
| `pibt_active_bag_replay` | `hold_when_sipp_moves` | `no_fault` | 16 | 0.152 |
| `pibt_active_bag_replay` | `buffer_capacity_branch_gap` | `buffer_capacity` | 13 | 0.124 |
| `pibt_active_bag_replay` | `hold_when_sipp_moves` | `repair_window` | 13 | 0.124 |
| `pibt_active_bag_replay` | `hold_when_sipp_moves` | `merge_group` | 12 | 0.114 |
| `fallback_event` | `hold_when_sipp_moves` | `merge_group` | 10 | 0.196 |
| `fallback_event` | `hold_when_sipp_moves` | `repair_window` | 10 | 0.196 |
| `pibt_active_bag_replay` | `hold_when_sipp_moves` | `static_fault` | 10 | 0.095 |
| `edge_score_event` | `hold_when_sipp_moves` | `merge_group` | 9 | 0.191 |
| `fallback_event` | `wrong_branch_vs_sipp` | `merge_group` | 9 | 0.176 |

## Interpretation

The current learning/prototype policy is not failing because of post-shield safety: the matched rows remain conflict-free. The gap is a completion and coordination gap. In failed task-scenario rows, rolling-horizon SIPP has a feasible route while the local policy either exhausts the decision horizon, holds when the SIPP teacher advances, or chooses a branch that later cannot recover within the local event policy.

This means the next useful work is not PPO/MAPPO. The next useful work is teacher-slice expansion and feature/oracle diagnosis: SIPP next-hop ranks, downstream reservation pressure, deadline slack, active fault/repair state, merge-group pressure, and no-safe-action risk labels.

## Artifacts

- Failed task inventory: `outputs/tables/g2_failed_task_inventory.csv`
- First divergence by task: `outputs/tables/g2_first_divergence_by_task.csv`
- Decision slices: `outputs/tables/g2_policy_vs_sipp_decision_slices.csv`
- Failure slices: `outputs/tables/g2_decision_failure_slices.csv`
- Policy-vs-SIPP counterfactual: `outputs/tables/g2_policy_vs_sipp_counterfactual.csv`
- Failure motif summary: `outputs/tables/g2_failure_motif_summary.csv`
- Family summary: `outputs/tables/g2_family_summary.csv`

## Gate Status

- failed task inventory: PASS
- first-divergence localization: PASS
- policy-vs-SIPP decision slices for EdgeScore/fallback event policies: PASS
- PIBT failure rows localized at task level: PASS
- A*-guided scripted policy included as sequential reference: PASS
- oracle upper-bound analysis: NOT DONE, belongs to G3

## Next Blocking Question

Can a local candidate-ranking oracle, using the same safe candidate set but richer SIPP-derived features, recover most of the EdgeScore `47` failed task-scenario rows? If not, the gap is probably horizon/memory/global-guidance limited rather than just model/data limited.

## Follow-up

- Build G3 teacher/oracle upper-bound tables before any RL fine-tuning.
- Add SIPP teacher ranks and downstream congestion fields to the next junction-slice dataset.
- Keep EdgeScore/BC/DAgger labeled as smoke/prototype until heldout closed-loop rows beat fallback and approach SIPP.
