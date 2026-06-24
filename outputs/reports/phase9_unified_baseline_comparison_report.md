# Phase9 Unified Baseline Comparison Diagnostic

Date: 2026-06-24

## Scope

This diagnostic builds a single Phase9 evidence table from the existing generated CSV outputs. It combines same-map policy/baseline outcome rows, real legacy event-scheduler Python/C++ parity, repeated native event runtime rows, repeated matched-baseline runtime rows, and aggregate parity coverage for the Phase2/Phase8 baseline families.

The table is intentionally an evidence index, not a final paper benchmark. Rows come from different scopes, and the first matched Phase9 rows are still limited to small no-fault/buffer-capacity/static-fault/repair-window/merge-group windows, so cross-policy ranking should wait for expanded matched maps, task windows, fault schedules, and multi-machine hardware-normalized timing.

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

| Scenario | Family | Tasks | Faults | Config | C++ planned | C++ active steps | Conflicts | Speedup | Parity |
|---|---|---:|---|---|---:|---:|---:|---:|---|
| legacy_first16 | rolling_horizon_sipp | 16 | none | none | 16 | 16 | 0 | 1.877902 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | none | 16 | 120 | 0 | 0.297503 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | none | 0 | 18599 | 0 | 0.699152 | True |
| legacy_first16 | edge_score_event | 16 | none | none | 16 | 173 | 0 | 1.979724 | True |
| legacy_first16 | fallback_event | 16 | none | none | 15 | 168 | 0 | 1.042741 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | none | nodes=28:2;47:2 | 16 | 16 | 0 | 0.209223 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | none | nodes=28:2;47:2 | 16 | 120 | 0 | 0.265011 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | none | nodes=28:2;47:2 | 0 | 18599 | 0 | 0.742965 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | none | nodes=28:2;47:2 | 16 | 173 | 0 | 1.872421 | True |
| legacy_first16_buffer2 | fallback_event | 16 | none | nodes=28:2;47:2 | 15 | 168 | 0 | 0.922556 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | none | 32 | 32 | 0 | 0.291282 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | none | 32 | 248 | 0 | 0.351031 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | none | 0 | 41032 | 0 | 0.802410 | True |
| legacy_first32 | edge_score_event | 32 | none | none | 24 | 330 | 0 | 2.970513 | True |
| legacy_first32 | fallback_event | 32 | none | none | 25 | 346 | 0 | 0.986246 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | 16->17 | none | 16 | 16 | 0 | 0.306361 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | 16->17 | none | 16 | 129 | 0 | 0.255419 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | 16->17 | none | 0 | 22378 | 0 | 0.795140 | True |
| legacy_offset32_static16 | edge_score_event | 16 | 16->17 | none | 12 | 205 | 0 | 2.379172 | True |
| legacy_offset32_static16 | fallback_event | 16 | 16->17 | none | 12 | 193 | 0 | 1.173032 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | 28->47@[0.000,12000.000) | none | 32 | 32 | 0 | 0.361366 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | 28->47@[0.000,12000.000) | none | 32 | 265 | 0 | 0.337341 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | 28->47@[0.000,12000.000) | none | 0 | 50808 | 0 | 0.828779 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | 28->47@[0.000,12000.000) | none | 15 | 323 | 0 | 2.468076 | True |
| legacy_offset64_repair32 | fallback_event | 32 | 28->47@[0.000,12000.000) | none | 13 | 321 | 0 | 1.183263 | True |
| legacy_offset64_merge32 | rolling_horizon_sipp | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 32 | 32 | 0 | 0.272151 | True |
| legacy_offset64_merge32 | periodic_replanning_sipp | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 32 | 260 | 0 | 0.341807 | True |
| legacy_offset64_merge32 | pibt_active_bag_replay | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 0 | 51876 | 0 | 0.690858 | True |
| legacy_offset64_merge32 | edge_score_event | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 14 | 332 | 0 | 2.625963 | True |
| legacy_offset64_merge32 | fallback_event | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 13 | 334 | 0 | 1.265459 | True |

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

## Matched Runtime Evidence

| Scenario | Family | Tasks | Config | Repeats | C++ seconds mean+/-95% CI | C++ active steps/s | Speedup | Parity |
|---|---|---:|---|---:|---:|---:|---:|---|
| legacy_first16 | rolling_horizon_sipp | 16 | none | 3 | 0.021014+/-0.001456 | 761.41 | 0.815135 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | 3 | 0.123583+/-0.005025 | 971.01 | 0.323621 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | 3 | 5.118390+/-0.050057 | 3633.76 | 0.874707 | True |
| legacy_first16 | edge_score_event | 16 | none | 3 | 0.042315+/-0.001144 | 4088.38 | 2.178417 | True |
| legacy_first16 | fallback_event | 16 | none | 3 | 0.035067+/-0.000998 | 4790.81 | 0.981890 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | nodes=28:2;47:2 | 3 | 0.021098+/-0.001314 | 758.38 | 0.363502 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | nodes=28:2;47:2 | 3 | 0.123514+/-0.002730 | 971.55 | 0.339373 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | nodes=28:2;47:2 | 3 | 5.014463+/-0.038680 | 3709.07 | 0.867402 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | nodes=28:2;47:2 | 3 | 0.042310+/-0.000886 | 4088.87 | 2.122391 | True |
| legacy_first16_buffer2 | fallback_event | 16 | nodes=28:2;47:2 | 3 | 0.035400+/-0.002824 | 4745.79 | 0.956466 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | 3 | 0.054420+/-0.001007 | 588.02 | 0.341220 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | 3 | 0.301526+/-0.004548 | 822.48 | 0.345673 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | 3 | 9.189207+/-0.160361 | 4465.24 | 0.879926 | True |
| legacy_first32 | edge_score_event | 32 | none | 3 | 0.105542+/-0.020364 | 3126.72 | 1.914238 | True |
| legacy_first32 | fallback_event | 32 | none | 3 | 0.102091+/-0.021442 | 3389.14 | 0.819435 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | none | 3 | 0.041291+/-0.005453 | 387.50 | 0.277139 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | none | 3 | 0.201431+/-0.044404 | 640.42 | 0.266205 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | none | 3 | 7.232646+/-0.345710 | 3094.03 | 0.795843 | True |
| legacy_offset32_static16 | edge_score_event | 16 | none | 3 | 0.059740+/-0.000361 | 3431.56 | 2.032006 | True |
| legacy_offset32_static16 | fallback_event | 16 | none | 3 | 0.052085+/-0.005544 | 3705.51 | 1.019637 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | none | 3 | 0.070361+/-0.005991 | 454.80 | 0.323890 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | none | 3 | 0.512115+/-0.046332 | 517.46 | 0.270492 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | none | 3 | 13.932004+/-0.132094 | 3646.86 | 0.842491 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | none | 3 | 0.078834+/-0.019343 | 4097.22 | 2.370292 | True |
| legacy_offset64_repair32 | fallback_event | 32 | none | 3 | 0.078506+/-0.010178 | 4088.85 | 0.947758 | True |
| legacy_offset64_merge32 | rolling_horizon_sipp | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 0.094002+/-0.018388 | 340.42 | 0.321433 | True |
| legacy_offset64_merge32 | periodic_replanning_sipp | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 0.524836+/-0.053653 | 495.39 | 0.296311 | True |
| legacy_offset64_merge32 | pibt_active_bag_replay | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 13.424489+/-0.235170 | 3864.28 | 0.845053 | True |
| legacy_offset64_merge32 | edge_score_event | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 0.083723+/-0.012908 | 3965.45 | 2.451947 | True |
| legacy_offset64_merge32 | fallback_event | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 0.058397+/-0.001449 | 5719.50 | 1.301487 | True |

## Parity Coverage

| Family | Source rows | Passing rows | Safety | Source |
|---|---:|---:|---|---|
| sipp_planner | 11 | 11 | True | `outputs/tables/phase2_cpp_sipp_parity.csv` |
| rolling_horizon_sipp | 13 | 13 | True | `outputs/tables/phase2_cpp_rolling_horizon_parity.csv` |
| periodic_replanning_sipp | 9 | 9 | True | `outputs/tables/phase2_periodic_replanning_parity.csv` |
| pibt_active_bag_replay | 7 | 7 | True | `outputs/tables/phase2_pibt_active_bag_replay_parity.csv` |
| phase8_synthetic_event_scheduler | 10 | 10 | True | `outputs/tables/phase8_native_cpp_event_parity.csv` |
| phase8_randomized_synthetic | 5 | 5 | True | `outputs/tables/phase8_native_cpp_randomized_parity.csv` |
| phase8_legacy_event_scheduler | 6 | 6 | True | `outputs/tables/phase8_legacy_event_parity.csv` |
| phase9_matched_baseline_comparison | 30 | 30 | True | `outputs/tables/phase9_matched_baseline_comparison.csv` |
| phase9_runtime_scaling | 8 | 8 | True | `outputs/tables/phase9_event_runtime_scaling.csv` |
| phase9_matched_runtime_scaling | 30 | 30 | True | `outputs/tables/phase9_matched_runtime_scaling.csv` |

## Gate Status

- unified outcome rows: `17`
- matched baseline rows: `30`
- matched baseline runtime rows: `30`
- native event parity/runtime rows: `14`
- baseline-family parity summaries: `10`
- policies/baselines surfaced: `astar_guided, dagger_bc, edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, reference_astar, rolling_horizon_sipp`
- parity families surfaced: `periodic_replanning_sipp, phase8_legacy_event_scheduler, phase8_randomized_synthetic, phase8_synthetic_event_scheduler, phase9_matched_baseline_comparison, phase9_matched_runtime_scaling, phase9_runtime_scaling, pibt_active_bag_replay, rolling_horizon_sipp, sipp_planner`
- all reported post-shield conflicts are zero: PASS
- native event Python/C++ parity rows pass: PASS
- baseline-family parity summaries pass: PASS
- median C++ decision-throughput speedup in runtime rows: `0.914x`
- matched paper-grade Phase9 comparison: not covered
- matched merge-group scenario: covered
- repeated matched-baseline runtime timing with 95% CI: covered

## Remaining Work

- add a separate real heldout airport map when fixture data is available
- expand timing to multi-machine hardware-normalized runs and confidence intervals before paper-grade speed claims
