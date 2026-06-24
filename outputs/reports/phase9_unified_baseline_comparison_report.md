# Phase9 Unified Baseline Comparison Diagnostic

Date: 2026-06-24

## Scope

This diagnostic builds a single Phase9 evidence table from the existing generated CSV outputs. It combines same-map policy/baseline outcome rows, real legacy event-scheduler Python/C++ parity, heldout-like synthetic matched rows, dense active-bag PIBT stress rows, randomized-topology PIBT stress rows, randomized-topology matched baseline rows, repeated native event runtime rows, repeated matched-baseline runtime rows, and aggregate parity coverage for the Phase2/Phase8 baseline families.

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
| legacy_first16 | rolling_horizon_sipp | 16 | none | none | 16 | 16 | 0 | 1.961098 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | none | 16 | 120 | 0 | 0.364674 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | none | 0 | 19149 | 0 | 0.749275 | True |
| legacy_first16 | edge_score_event | 16 | none | none | 16 | 173 | 0 | 2.288167 | True |
| legacy_first16 | fallback_event | 16 | none | none | 15 | 168 | 0 | 1.000929 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | none | nodes=28:2;47:2 | 16 | 16 | 0 | 0.373247 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | none | nodes=28:2;47:2 | 16 | 120 | 0 | 0.322078 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | none | nodes=28:2;47:2 | 0 | 19149 | 0 | 0.962385 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | none | nodes=28:2;47:2 | 16 | 173 | 0 | 2.918339 | True |
| legacy_first16_buffer2 | fallback_event | 16 | none | nodes=28:2;47:2 | 15 | 168 | 0 | 1.328441 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | none | 32 | 32 | 0 | 0.253821 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | none | 32 | 248 | 0 | 0.444682 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | none | 10 | 29055 | 0 | 1.061465 | True |
| legacy_first32 | edge_score_event | 32 | none | none | 24 | 330 | 0 | 2.953811 | True |
| legacy_first32 | fallback_event | 32 | none | none | 25 | 346 | 0 | 1.193045 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | 16->17 | none | 16 | 16 | 0 | 0.324453 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | 16->17 | none | 16 | 129 | 0 | 0.328663 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | 16->17 | none | 1 | 20706 | 0 | 0.966601 | True |
| legacy_offset32_static16 | edge_score_event | 16 | 16->17 | none | 12 | 205 | 0 | 2.542997 | True |
| legacy_offset32_static16 | fallback_event | 16 | 16->17 | none | 12 | 193 | 0 | 1.551260 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | 28->47@[0.000,12000.000) | none | 32 | 32 | 0 | 0.359808 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | 28->47@[0.000,12000.000) | none | 32 | 265 | 0 | 0.304254 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | 28->47@[0.000,12000.000) | none | 14 | 27600 | 0 | 1.023950 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | 28->47@[0.000,12000.000) | none | 15 | 323 | 0 | 2.654798 | True |
| legacy_offset64_repair32 | fallback_event | 32 | 28->47@[0.000,12000.000) | none | 13 | 321 | 0 | 1.195490 | True |
| legacy_offset64_merge32 | rolling_horizon_sipp | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 32 | 32 | 0 | 0.374529 | True |
| legacy_offset64_merge32 | periodic_replanning_sipp | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 32 | 260 | 0 | 0.403129 | True |
| legacy_offset64_merge32 | pibt_active_bag_replay | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 14 | 27600 | 0 | 1.034889 | True |
| legacy_offset64_merge32 | edge_score_event | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 14 | 332 | 0 | 2.623353 | True |
| legacy_offset64_merge32 | fallback_event | 32 | none | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 13 | 334 | 0 | 1.570873 | True |

## Synthetic Matched Evidence

| Scenario | Family | Tasks | Config | C++ planned | C++ active steps | Conflicts | Speedup | Parity | Notes |
|---|---|---:|---|---:|---:|---:|---:|---|---|
| synthetic_seed7_medium_repair | rolling_horizon_sipp | 18 | none | 18 | 18 | 0 | 7.205706 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed7_medium_repair | periodic_replanning_sipp | 18 | none | 18 | 54 | 0 | 0.455007 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed7_medium_repair | pibt_active_bag_replay | 18 | none | 18 | 56 | 0 | 0.571760 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed7_medium_repair | edge_score_event | 18 | none | 18 | 55 | 0 | 2.834633 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed7_medium_repair | fallback_event | 18 | none | 18 | 55 | 0 | 0.604793 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed11_dense_multi_repair | rolling_horizon_sipp | 24 | none | 24 | 24 | 0 | 0.638813 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed11_dense_multi_repair | periodic_replanning_sipp | 24 | none | 24 | 87 | 0 | 0.564805 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed11_dense_multi_repair | pibt_active_bag_replay | 24 | none | 24 | 292 | 0 | 0.543914 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed11_dense_multi_repair | edge_score_event | 24 | none | 15 | 125 | 0 | 1.848325 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed11_dense_multi_repair | fallback_event | 24 | none | 15 | 125 | 0 | 0.803519 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed17_static_plus_repair | rolling_horizon_sipp | 20 | none | 20 | 20 | 0 | 0.685127 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed17_static_plus_repair | periodic_replanning_sipp | 20 | none | 20 | 76 | 0 | 0.453830 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed17_static_plus_repair | pibt_active_bag_replay | 20 | none | 20 | 324 | 0 | 0.549985 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed17_static_plus_repair | edge_score_event | 20 | none | 12 | 97 | 0 | 2.099960 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed17_static_plus_repair | fallback_event | 20 | none | 12 | 97 | 0 | 0.752581 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed23_repeated_repair | rolling_horizon_sipp | 22 | none | 22 | 22 | 0 | 0.529154 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed23_repeated_repair | periodic_replanning_sipp | 22 | none | 22 | 74 | 0 | 0.379923 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed23_repeated_repair | pibt_active_bag_replay | 22 | none | 22 | 187 | 0 | 0.542495 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed23_repeated_repair | edge_score_event | 22 | none | 20 | 85 | 0 | 1.696887 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed23_repeated_repair | fallback_event | 22 | none | 19 | 93 | 0 | 0.692667 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed31_merge_buffer | rolling_horizon_sipp | 26 | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 26 | 26 | 0 | 0.472314 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed31_merge_buffer | periodic_replanning_sipp | 26 | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 26 | 81 | 0 | 0.503433 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed31_merge_buffer | pibt_active_bag_replay | 26 | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 26 | 123 | 0 | 0.586935 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed31_merge_buffer | edge_score_event | 26 | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 22 | 109 | 0 | 1.826956 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |
| synthetic_seed31_merge_buffer | fallback_event | 26 | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 22 | 109 | 0 | 0.863828 | True | fixed-seed synthetic heldout-like map; not a separate real airport map |

## Dense PIBT Stress Evidence

| Scenario | Tasks | Faults | Config | C++ planned | C++ active steps | Conflicts | Speedup | Parity |
|---|---:|---|---|---:|---:|---:|---:|---|
| dense_pibt_seed101_low_spacing | 30 | none | none | 30 | 191 | 0 | 1.687353 | True |
| dense_pibt_seed103_low_spacing | 32 | none | none | 32 | 173 | 0 | 0.537604 | True |
| dense_pibt_seed107_static | 32 | 4->7 | none | 32 | 238 | 0 | 0.539183 | True |
| dense_pibt_seed109_static | 34 | 5->8 | none | 34 | 359 | 0 | 0.576582 | True |
| dense_pibt_seed113_repair | 34 | 4->8@[2.000,13.000) | none | 34 | 244 | 0 | 0.559456 | True |
| dense_pibt_seed127_multi_repair | 36 | 4->8@[3.000,10.000);8->9@[9.000,20.000) | none | 36 | 403 | 0 | 0.528108 | True |
| dense_pibt_seed131_merge_buffer | 36 | 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 36 | 323 | 0 | 0.575185 | True |
| dense_pibt_seed137_merge_buffer | 38 | 5->8@[3.000,16.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 38 | 433 | 0 | 0.543209 | True |
| dense_pibt_seed139_static_repair | 34 | 4->7 | none | 34 | 364 | 0 | 0.643072 | True |
| dense_pibt_seed149_repeated_repair | 36 | 4->8@[3.000,8.000);4->8@[14.000,21.000);8->9@[9.000,15.000) | none | 36 | 517 | 0 | 0.636273 | True |
| dense_pibt_seed151_overload | 40 | none | none | 40 | 365 | 0 | 0.551148 | True |
| dense_pibt_seed157_overload_merge | 40 | 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 40 | 435 | 0 | 0.609922 | True |

## Random Topology PIBT Stress Evidence

| Scenario | Tasks | Faults | Config | C++ planned | C++ active steps | Conflicts | Speedup | Parity | Notes |
|---|---:|---|---|---:|---:|---:|---:|---|---|
| random_topo_seed211_wide_uniform | 36 | none | none | 36 | 200 | 0 | 1.384507 | True | Random DAG-like topology layers=3-4-4-3-2; source_mode=uniform; goal_mode=uniform; branch=0.45; shortcut=0.12; sources=0:8;1:17;2:11; goals=14:14;15:22. |
| random_topo_seed223_skewed_bottleneck | 40 | none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 40 | 166 | 0 | 0.690095 | True | Random DAG-like topology layers=4-3-5-3-2; source_mode=skewed; goal_mode=skewed; branch=0.5; shortcut=0.18; sources=0:30;1:5;2:2;3:3; goals=15:27;16:13. |
| random_topo_seed227_burst_repair | 42 | 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 42 | 168 | 0 | 0.618070 | True | Random DAG-like topology layers=3-5-3-5-2; source_mode=burst; goal_mode=alternating; branch=0.42; shortcut=0.1; sources=0:18;1:12;2:12; goals=16:21;17:21. |
| random_topo_seed229_static_alt | 44 | 10->12 | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 44 | 311 | 0 | 0.601670 | True | Random DAG-like topology layers=4-4-4-4-3; source_mode=alternating; goal_mode=uniform; branch=0.38; shortcut=0.16; sources=1:22;3:22; goals=16:18;17:17;18:9. |
| random_topo_seed233_shortcut_dense | 48 | 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 48 | 191 | 0 | 0.727140 | True | Random DAG-like topology layers=5-5-4-5-3; source_mode=skewed; goal_mode=alternating; branch=0.6; shortcut=0.3; sources=0:37;1:5;2:2;3:1;4:3; goals=19:16;20:16;21:16. |
| random_topo_seed239_sparse_repair | 34 | 3->8@[4.000,18.000) | none | 34 | 245 | 0 | 0.579494 | True | Random DAG-like topology layers=3-3-3-3-2; source_mode=burst; goal_mode=skewed; branch=0.22; shortcut=0.05; sources=0:12;1:12;2:10; goals=12:25;13:9. |

## Random Topology Matched Evidence

| Scenario | Family | Tasks | Faults | Config | C++ planned | C++ active steps | Conflicts | Speedup | Parity | Notes |
|---|---|---:|---|---|---:|---:|---:|---:|---|---|
| random_topo_seed211_wide_uniform | rolling_horizon_sipp | 36 | none | none | 36 | 36 | 0 | 1.842218 | True | Random DAG-like matched family row; layers=3-4-4-3-2; source_mode=uniform; goal_mode=uniform; sources=0:8;1:17;2:11; goals=14:14;15:22. |
| random_topo_seed211_wide_uniform | periodic_replanning_sipp | 36 | none | none | 36 | 140 | 0 | 0.404959 | True | Random DAG-like matched family row; layers=3-4-4-3-2; source_mode=uniform; goal_mode=uniform; sources=0:8;1:17;2:11; goals=14:14;15:22. |
| random_topo_seed211_wide_uniform | pibt_active_bag_replay | 36 | none | none | 36 | 200 | 0 | 0.659899 | True | Random DAG-like matched family row; layers=3-4-4-3-2; source_mode=uniform; goal_mode=uniform; sources=0:8;1:17;2:11; goals=14:14;15:22. |
| random_topo_seed211_wide_uniform | edge_score_event | 36 | none | none | 27 | 163 | 0 | 3.045166 | True | Random DAG-like matched family row; layers=3-4-4-3-2; source_mode=uniform; goal_mode=uniform; sources=0:8;1:17;2:11; goals=14:14;15:22. |
| random_topo_seed211_wide_uniform | fallback_event | 36 | none | none | 27 | 161 | 0 | 1.038763 | True | Random DAG-like matched family row; layers=3-4-4-3-2; source_mode=uniform; goal_mode=uniform; sources=0:8;1:17;2:11; goals=14:14;15:22. |
| random_topo_seed223_skewed_bottleneck | rolling_horizon_sipp | 40 | none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 40 | 40 | 0 | 0.505405 | True | Random DAG-like matched family row; layers=4-3-5-3-2; source_mode=skewed; goal_mode=skewed; sources=0:30;1:5;2:2;3:3; goals=15:27;16:13. |
| random_topo_seed223_skewed_bottleneck | periodic_replanning_sipp | 40 | none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 40 | 140 | 0 | 0.451948 | True | Random DAG-like matched family row; layers=4-3-5-3-2; source_mode=skewed; goal_mode=skewed; sources=0:30;1:5;2:2;3:3; goals=15:27;16:13. |
| random_topo_seed223_skewed_bottleneck | pibt_active_bag_replay | 40 | none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 40 | 166 | 0 | 0.589652 | True | Random DAG-like matched family row; layers=4-3-5-3-2; source_mode=skewed; goal_mode=skewed; sources=0:30;1:5;2:2;3:3; goals=15:27;16:13. |
| random_topo_seed223_skewed_bottleneck | edge_score_event | 40 | none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 26 | 178 | 0 | 2.675707 | True | Random DAG-like matched family row; layers=4-3-5-3-2; source_mode=skewed; goal_mode=skewed; sources=0:30;1:5;2:2;3:3; goals=15:27;16:13. |
| random_topo_seed223_skewed_bottleneck | fallback_event | 40 | none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 24 | 170 | 0 | 1.098874 | True | Random DAG-like matched family row; layers=4-3-5-3-2; source_mode=skewed; goal_mode=skewed; sources=0:30;1:5;2:2;3:3; goals=15:27;16:13. |
| random_topo_seed227_burst_repair | rolling_horizon_sipp | 42 | 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 42 | 42 | 0 | 0.426495 | True | Random DAG-like matched family row; layers=3-5-3-5-2; source_mode=burst; goal_mode=alternating; sources=0:18;1:12;2:12; goals=16:21;17:21. |
| random_topo_seed227_burst_repair | periodic_replanning_sipp | 42 | 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 42 | 156 | 0 | 0.436187 | True | Random DAG-like matched family row; layers=3-5-3-5-2; source_mode=burst; goal_mode=alternating; sources=0:18;1:12;2:12; goals=16:21;17:21. |
| random_topo_seed227_burst_repair | pibt_active_bag_replay | 42 | 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 42 | 168 | 0 | 0.595260 | True | Random DAG-like matched family row; layers=3-5-3-5-2; source_mode=burst; goal_mode=alternating; sources=0:18;1:12;2:12; goals=16:21;17:21. |
| random_topo_seed227_burst_repair | edge_score_event | 42 | 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 15 | 136 | 0 | 2.849804 | True | Random DAG-like matched family row; layers=3-5-3-5-2; source_mode=burst; goal_mode=alternating; sources=0:18;1:12;2:12; goals=16:21;17:21. |
| random_topo_seed227_burst_repair | fallback_event | 42 | 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 15 | 135 | 0 | 1.215045 | True | Random DAG-like matched family row; layers=3-5-3-5-2; source_mode=burst; goal_mode=alternating; sources=0:18;1:12;2:12; goals=16:21;17:21. |
| random_topo_seed229_static_alt | rolling_horizon_sipp | 44 | 10->12 | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 44 | 44 | 0 | 0.534827 | True | Random DAG-like matched family row; layers=4-4-4-4-3; source_mode=alternating; goal_mode=uniform; sources=1:22;3:22; goals=16:18;17:17;18:9. |
| random_topo_seed229_static_alt | periodic_replanning_sipp | 44 | 10->12 | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 44 | 162 | 0 | 0.521209 | True | Random DAG-like matched family row; layers=4-4-4-4-3; source_mode=alternating; goal_mode=uniform; sources=1:22;3:22; goals=16:18;17:17;18:9. |
| random_topo_seed229_static_alt | pibt_active_bag_replay | 44 | 10->12 | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 44 | 311 | 0 | 0.682171 | True | Random DAG-like matched family row; layers=4-4-4-4-3; source_mode=alternating; goal_mode=uniform; sources=1:22;3:22; goals=16:18;17:17;18:9. |
| random_topo_seed229_static_alt | edge_score_event | 44 | 10->12 | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 23 | 190 | 0 | 2.544422 | True | Random DAG-like matched family row; layers=4-4-4-4-3; source_mode=alternating; goal_mode=uniform; sources=1:22;3:22; goals=16:18;17:17;18:9. |
| random_topo_seed229_static_alt | fallback_event | 44 | 10->12 | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 21 | 191 | 0 | 1.200068 | True | Random DAG-like matched family row; layers=4-4-4-4-3; source_mode=alternating; goal_mode=uniform; sources=1:22;3:22; goals=16:18;17:17;18:9. |
| random_topo_seed233_shortcut_dense | rolling_horizon_sipp | 48 | 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 48 | 48 | 0 | 0.612399 | True | Random DAG-like matched family row; layers=5-5-4-5-3; source_mode=skewed; goal_mode=alternating; sources=0:37;1:5;2:2;3:1;4:3; goals=19:16;20:16;21:16. |
| random_topo_seed233_shortcut_dense | periodic_replanning_sipp | 48 | 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 48 | 186 | 0 | 0.498692 | True | Random DAG-like matched family row; layers=5-5-4-5-3; source_mode=skewed; goal_mode=alternating; sources=0:37;1:5;2:2;3:1;4:3; goals=19:16;20:16;21:16. |
| random_topo_seed233_shortcut_dense | pibt_active_bag_replay | 48 | 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 48 | 191 | 0 | 0.694545 | True | Random DAG-like matched family row; layers=5-5-4-5-3; source_mode=skewed; goal_mode=alternating; sources=0:37;1:5;2:2;3:1;4:3; goals=19:16;20:16;21:16. |
| random_topo_seed233_shortcut_dense | edge_score_event | 48 | 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 25 | 149 | 0 | 2.429769 | True | Random DAG-like matched family row; layers=5-5-4-5-3; source_mode=skewed; goal_mode=alternating; sources=0:37;1:5;2:2;3:1;4:3; goals=19:16;20:16;21:16. |
| random_topo_seed233_shortcut_dense | fallback_event | 48 | 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 26 | 145 | 0 | 1.137189 | True | Random DAG-like matched family row; layers=5-5-4-5-3; source_mode=skewed; goal_mode=alternating; sources=0:37;1:5;2:2;3:1;4:3; goals=19:16;20:16;21:16. |
| random_topo_seed239_sparse_repair | rolling_horizon_sipp | 34 | 3->8@[4.000,18.000) | none | 34 | 34 | 0 | 0.599932 | True | Random DAG-like matched family row; layers=3-3-3-3-2; source_mode=burst; goal_mode=skewed; sources=0:12;1:12;2:10; goals=12:25;13:9. |
| random_topo_seed239_sparse_repair | periodic_replanning_sipp | 34 | 3->8@[4.000,18.000) | none | 34 | 133 | 0 | 0.514740 | True | Random DAG-like matched family row; layers=3-3-3-3-2; source_mode=burst; goal_mode=skewed; sources=0:12;1:12;2:10; goals=12:25;13:9. |
| random_topo_seed239_sparse_repair | pibt_active_bag_replay | 34 | 3->8@[4.000,18.000) | none | 34 | 245 | 0 | 0.604096 | True | Random DAG-like matched family row; layers=3-3-3-3-2; source_mode=burst; goal_mode=skewed; sources=0:12;1:12;2:10; goals=12:25;13:9. |
| random_topo_seed239_sparse_repair | edge_score_event | 34 | 3->8@[4.000,18.000) | none | 8 | 99 | 0 | 2.146648 | True | Random DAG-like matched family row; layers=3-3-3-3-2; source_mode=burst; goal_mode=skewed; sources=0:12;1:12;2:10; goals=12:25;13:9. |
| random_topo_seed239_sparse_repair | fallback_event | 34 | 3->8@[4.000,18.000) | none | 8 | 87 | 0 | 1.058976 | True | Random DAG-like matched family row; layers=3-3-3-3-2; source_mode=burst; goal_mode=skewed; sources=0:12;1:12;2:10; goals=12:25;13:9. |

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
| legacy_first16 | rolling_horizon_sipp | 16 | none | 3 | 0.020762+/-0.000635 | 770.65 | 0.958001 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | 3 | 0.123673+/-0.002347 | 970.30 | 0.381806 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | 3 | 5.473058+/-0.356821 | 3498.78 | 0.989300 | True |
| legacy_first16 | edge_score_event | 16 | none | 3 | 0.046289+/-0.010349 | 3737.41 | 2.678646 | True |
| legacy_first16 | fallback_event | 16 | none | 3 | 0.037728+/-0.008442 | 4452.89 | 1.216439 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | nodes=28:2;47:2 | 3 | 0.023807+/-0.003231 | 672.08 | 0.463894 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | nodes=28:2;47:2 | 3 | 0.153118+/-0.009644 | 783.71 | 0.396897 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | nodes=28:2;47:2 | 3 | 5.481962+/-0.137094 | 3493.09 | 0.983451 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | nodes=28:2;47:2 | 3 | 0.046354+/-0.005939 | 3732.18 | 2.571506 | True |
| legacy_first16_buffer2 | fallback_event | 16 | nodes=28:2;47:2 | 3 | 0.043014+/-0.006198 | 3905.68 | 1.039700 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | 3 | 0.057958+/-0.010656 | 552.12 | 0.400752 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | 3 | 0.373462+/-0.041650 | 664.06 | 0.370006 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | 3 | 9.304883+/-0.274150 | 3122.55 | 1.017782 | True |
| legacy_first32 | edge_score_event | 32 | none | 3 | 0.090031+/-0.021339 | 3665.40 | 2.663006 | True |
| legacy_first32 | fallback_event | 32 | none | 3 | 0.072585+/-0.016259 | 4766.84 | 1.370598 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | none | 3 | 0.034048+/-0.002611 | 469.93 | 0.279094 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | none | 3 | 0.204520+/-0.022839 | 630.74 | 0.292971 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | none | 3 | 6.584405+/-0.077422 | 3144.70 | 1.005857 | True |
| legacy_offset32_static16 | edge_score_event | 16 | none | 3 | 0.043164+/-0.006948 | 4749.30 | 3.368758 | True |
| legacy_offset32_static16 | fallback_event | 16 | none | 3 | 0.047887+/-0.012981 | 4030.32 | 1.089840 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | none | 3 | 0.074276+/-0.015058 | 430.83 | 0.366999 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | none | 3 | 0.467732+/-0.024789 | 566.56 | 0.307363 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | none | 3 | 8.864358+/-0.669878 | 3113.59 | 1.001900 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | none | 3 | 0.066690+/-0.008639 | 4843.27 | 3.195143 | True |
| legacy_offset64_repair32 | fallback_event | 32 | none | 3 | 0.070375+/-0.022678 | 4561.27 | 1.286551 | True |
| legacy_offset64_merge32 | rolling_horizon_sipp | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 0.097435+/-0.017881 | 328.43 | 0.344351 | True |
| legacy_offset64_merge32 | periodic_replanning_sipp | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 0.533252+/-0.108590 | 487.57 | 0.348144 | True |
| legacy_offset64_merge32 | pibt_active_bag_replay | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 8.687420+/-0.235647 | 3177.01 | 1.022966 | True |
| legacy_offset64_merge32 | edge_score_event | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 0.068428+/-0.010076 | 4851.80 | 3.227028 | True |
| legacy_offset64_merge32 | fallback_event | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 3 | 0.060767+/-0.004428 | 5496.40 | 1.606867 | True |

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
| phase9_dense_pibt_stress_sweep | 12 | 12 | True | `outputs/tables/phase9_dense_pibt_stress_sweep.csv` |
| phase9_random_topology_pibt_stress_sweep | 6 | 6 | True | `outputs/tables/phase9_random_topology_pibt_stress_sweep.csv` |
| phase9_random_topology_matched_baseline_comparison | 30 | 30 | True | `outputs/tables/phase9_random_topology_matched_baseline_comparison.csv` |

## Gate Status

- unified outcome rows: `17`
- matched baseline rows: `30`
- synthetic matched baseline rows: `25`
- dense PIBT stress rows: `12`
- random topology PIBT stress rows: `6`
- random topology matched baseline rows: `30`
- matched baseline runtime rows: `30`
- native event parity/runtime rows: `14`
- baseline-family parity summaries: `13`
- policies/baselines surfaced: `astar_guided, dagger_bc, edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, reference_astar, rolling_horizon_sipp`
- parity families surfaced: `periodic_replanning_sipp, phase8_legacy_event_scheduler, phase8_randomized_synthetic, phase8_synthetic_event_scheduler, phase9_dense_pibt_stress_sweep, phase9_matched_baseline_comparison, phase9_matched_runtime_scaling, phase9_random_topology_matched_baseline_comparison, phase9_random_topology_pibt_stress_sweep, phase9_runtime_scaling, pibt_active_bag_replay, rolling_horizon_sipp, sipp_planner`
- gate-scoped post-shield conflicts are zero: PASS
- all reported post-shield conflicts are zero: PASS
- dense PIBT stress Python/C++ parity rows pass: PASS
- dense PIBT stress rows are safety-clean: PASS
- random topology PIBT stress Python/C++ parity rows pass: PASS
- random topology PIBT stress rows are safety-clean: PASS
- random topology matched baseline Python/C++ parity rows pass: PASS
- random topology matched baseline rows are safety-clean: PASS
- native event Python/C++ parity rows pass: PASS
- baseline-family parity summaries pass: PASS
- median C++ decision-throughput speedup in runtime rows: `1.065x`
- matched paper-grade Phase9 comparison: not covered
- matched merge-group scenario: covered
- repeated matched-baseline runtime timing with 95% CI: covered
- heldout-like synthetic matched comparison: covered
- dense active-bag PIBT stress sweep: covered
- randomized topology/task-source PIBT stress sweep: covered
- randomized topology/task-source matched baseline comparison: covered

## Remaining Work

- add a separate real heldout airport map when fixture data is available
- broaden beyond DAG-like synthetic topologies and fixture task-source models before paper-grade stress claims
- expand timing to multi-machine hardware-normalized runs and confidence intervals before paper-grade speed claims
