# Phase9 Unified Baseline Comparison Diagnostic

Date: 2026-06-23

## Scope

This diagnostic builds a single Phase9 evidence table from the existing generated CSV outputs. It combines same-map policy/baseline outcome rows, real legacy event-scheduler Python/C++ parity, repeated native event runtime rows, and aggregate parity coverage for the Phase2/Phase8 baseline families.

The table is intentionally an evidence index, not a final paper benchmark. Rows come from different scopes, and the first matched Phase9 rows are still limited to small no-fault/buffer-capacity/static-fault/repair-window windows, so cross-policy ranking should wait for expanded matched maps, task windows, fault schedules, and hardware-normalized timing.

CSV: `outputs/tables/phase9_unified_baseline_comparison.csv`

## Outcome Evidence

| Case | Policy/Baseline | Tasks | Faults | Planned | Unplanned | Conflicts | Mean travel | Seconds |
|---|---|---:|---|---:|---:|---:|---:|---:|
| phase2_baseline_smoke | reference_astar | 128 | none | 113 | 15 | 0 | 51.529204 | 0.045239 |
| phase2_baseline_smoke | rolling_horizon_sipp | 128 | none | 128 | 0 | 0 | 87.705494 | 0.118812 |
| density_train_first8 | astar_guided | 8 | none | 8 | 0 | 0 | 49.750000 | 0.024638 |
| density_train_first8 | dagger_bc | 8 | none | 8 | 0 | 0 | 49.750000 | 0.013625 |
| density_train_first8 | rolling_horizon_sipp | 8 | none | 8 | 0 | 0 | 50.456509 | 0.005459 |
| density_heldout_next8 | astar_guided | 8 | none | 7 | 1 | 0 | 51.971429 | 0.029784 |
| density_heldout_next8 | dagger_bc | 8 | none | 7 | 1 | 0 | 51.971429 | 0.016962 |
| density_heldout_next8 | rolling_horizon_sipp | 8 | none | 8 | 0 | 0 | 57.765529 | 0.004197 |
| density_combined_first16 | astar_guided | 16 | none | 15 | 1 | 0 | 51.586667 | 0.064880 |
| density_combined_first16 | dagger_bc | 16 | none | 15 | 1 | 0 | 51.586667 | 0.041700 |
| density_combined_first16 | rolling_horizon_sipp | 16 | none | 16 | 0 | 0 | 52.740501 | 0.008298 |
| fault_alt_route_first8 | astar_guided | 8 | 16->17 | 8 | 0 | 0 | 51.850000 | 0.024471 |
| fault_alt_route_first8 | dagger_bc | 8 | 16->17 | 4 | 4 | 0 | 47.000000 | 0.097394 |
| fault_alt_route_first8 | rolling_horizon_sipp | 8 | 16->17 | 8 | 0 | 0 | 53.606509 | 0.002708 |
| fault_goal_exit_first8 | astar_guided | 8 | 28->47 | 0 | 8 | 0 | 0.000000 | 0.284781 |
| fault_goal_exit_first8 | dagger_bc | 8 | 28->47 | 0 | 8 | 0 | 0.000000 | 0.203590 |
| fault_goal_exit_first8 | rolling_horizon_sipp | 8 | 28->47 | 8 | 0 | 0 | 84.242655 | 0.005271 |

## Matched Baseline Evidence

| Scenario | Family | Tasks | Faults | Buffer | C++ planned | C++ active steps | Conflicts | Speedup | Parity |
|---|---|---:|---|---|---:|---:|---:|---:|---|
| legacy_first16 | rolling_horizon_sipp | 16 | none | none | 16 | 16 | 0 | 5.338645 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | none | 16 | 120 | 0 | 0.847620 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | none | 0 | 18599 | 0 | 0.808346 | True |
| legacy_first16 | edge_score_event | 16 | none | none | 16 | 173 | 0 | 2.086075 | True |
| legacy_first16 | fallback_event | 16 | none | none | 15 | 168 | 0 | 1.002151 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | none | 28:2;47:2 | 16 | 16 | 0 | 0.608293 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | none | 28:2;47:2 | 16 | 120 | 0 | 0.852381 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | none | 28:2;47:2 | 0 | 18599 | 0 | 0.820508 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | none | 28:2;47:2 | 16 | 173 | 0 | 2.126276 | True |
| legacy_first16_buffer2 | fallback_event | 16 | none | 28:2;47:2 | 15 | 168 | 0 | 1.065881 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | none | 32 | 32 | 0 | 0.829810 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | none | 32 | 248 | 0 | 0.733281 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | none | 0 | 41032 | 0 | 0.890613 | True |
| legacy_first32 | edge_score_event | 32 | none | none | 24 | 330 | 0 | 2.353723 | True |
| legacy_first32 | fallback_event | 32 | none | none | 25 | 346 | 0 | 1.029406 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | 16->17 | none | 16 | 16 | 0 | 0.948935 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | 16->17 | none | 16 | 129 | 0 | 0.637186 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | 16->17 | none | 0 | 22378 | 0 | 0.819749 | True |
| legacy_offset32_static16 | edge_score_event | 16 | 16->17 | none | 12 | 205 | 0 | 2.663386 | True |
| legacy_offset32_static16 | fallback_event | 16 | 16->17 | none | 12 | 193 | 0 | 0.928187 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | 28->47@[0.000,12000.000) | none | 32 | 32 | 0 | 1.020745 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | 28->47@[0.000,12000.000) | none | 32 | 265 | 0 | 0.709194 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | 28->47@[0.000,12000.000) | none | 0 | 50808 | 0 | 0.920311 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | 28->47@[0.000,12000.000) | none | 15 | 323 | 0 | 2.184377 | True |
| legacy_offset64_repair32 | fallback_event | 32 | 28->47@[0.000,12000.000) | none | 13 | 321 | 0 | 1.216787 | True |

## Legacy Event Parity Evidence

| Case | Policy | Tasks | Py planned | C++ planned | C++ decisions | Conflicts | Strict parity |
|---|---|---:|---:|---:|---:|---:|---|
| legacy_first16 | edge_score_event | 16 | 16 | 16 | 173 | 0 | True |
| legacy_first16 | fallback_event | 16 | 15 | 15 | 168 | 0 | True |
| legacy_offset32_static_fault | edge_score_event | 16 | 12 | 12 | 205 | 0 | True |
| legacy_offset32_static_fault | fallback_event | 16 | 12 | 12 | 193 | 0 | True |
| legacy_offset64_repair_window | edge_score_event | 16 | 9 | 9 | 150 | 0 | True |
| legacy_offset64_repair_window | fallback_event | 16 | 8 | 8 | 157 | 0 | True |

## Runtime Evidence

| Case | Policy | Tasks | C++ planned | C++ decisions | C++ seconds | C++ decisions/s | Speedup | Parity |
|---|---|---:|---:|---:|---:|---:|---:|---|
| legacy_first16 | edge_score_event | 16 | 16 | 173 | 0.039193 | 4414.06 | 2.366056 | True |
| legacy_first16 | fallback_event | 16 | 15 | 168 | 0.035081 | 4788.91 | 1.184355 | True |
| legacy_first32 | edge_score_event | 32 | 24 | 330 | 0.073843 | 4468.93 | 2.496110 | True |
| legacy_first32 | fallback_event | 32 | 25 | 346 | 0.065392 | 5291.13 | 1.126638 | True |
| legacy_first64 | edge_score_event | 64 | 41 | 695 | 0.146148 | 4755.45 | 2.680652 | True |
| legacy_first64 | fallback_event | 64 | 43 | 721 | 0.128189 | 5624.49 | 1.280642 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | 15 | 323 | 0.060607 | 5329.46 | 2.849495 | True |
| legacy_offset64_repair32 | fallback_event | 32 | 13 | 321 | 0.055447 | 5789.31 | 1.214987 | True |

## Parity Coverage

| Family | Source rows | Passing rows | Safety | Source |
|---|---:|---:|---|---|
| sipp_planner | 9 | 9 | True | `outputs/tables/phase2_cpp_sipp_parity.csv` |
| rolling_horizon_sipp | 12 | 12 | True | `outputs/tables/phase2_cpp_rolling_horizon_parity.csv` |
| periodic_replanning_sipp | 8 | 8 | True | `outputs/tables/phase2_periodic_replanning_parity.csv` |
| pibt_active_bag_replay | 6 | 6 | True | `outputs/tables/phase2_pibt_active_bag_replay_parity.csv` |
| phase8_synthetic_event_scheduler | 10 | 10 | True | `outputs/tables/phase8_native_cpp_event_parity.csv` |
| phase8_randomized_synthetic | 5 | 5 | True | `outputs/tables/phase8_native_cpp_randomized_parity.csv` |
| phase8_legacy_event_scheduler | 6 | 6 | True | `outputs/tables/phase8_legacy_event_parity.csv` |
| phase9_matched_baseline_comparison | 25 | 25 | True | `outputs/tables/phase9_matched_baseline_comparison.csv` |
| phase9_runtime_scaling | 8 | 8 | True | `outputs/tables/phase9_event_runtime_scaling.csv` |

## Gate Status

- unified outcome rows: `17`
- matched baseline rows: `25`
- native event parity/runtime rows: `14`
- baseline-family parity summaries: `9`
- policies/baselines surfaced: `astar_guided, dagger_bc, edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, reference_astar, rolling_horizon_sipp`
- parity families surfaced: `periodic_replanning_sipp, phase8_legacy_event_scheduler, phase8_randomized_synthetic, phase8_synthetic_event_scheduler, phase9_matched_baseline_comparison, phase9_runtime_scaling, pibt_active_bag_replay, rolling_horizon_sipp, sipp_planner`
- all reported post-shield conflicts are zero: PASS
- native event Python/C++ parity rows pass: PASS
- baseline-family parity summaries pass: PASS
- median C++ decision-throughput speedup in runtime rows: `1.823x`
- matched paper-grade Phase9 comparison: not covered

## Remaining Work

- extend matched Phase9 rows to merge-group scenarios once every included family accepts shared merge config
- add a separate real heldout airport map when fixture data is available
- add hardware-normalized repeated timing and confidence intervals for every compared baseline family
