# Phase9 Random Topology Matched Baseline Comparison

Date: 2026-06-24

## Scope

This diagnostic reruns the main Python/C++ baseline and event families on generated random DAG-like ICS topologies. It reuses the Phase9 random-topology case generator but expands coverage beyond PIBT-only stress to rolling-horizon SIPP, periodic replanning SIPP, PIBT active-bag replay, EdgeScore event replay, and fallback event replay.

CSV: `outputs/tables/phase9_random_topology_matched_baseline_comparison.csv`

These are synthetic topology/task-source stress rows, not separate real airport maps.

## Matched Rows

| Scenario | Layers | Family | Tasks | Edges | Faults | Config | Py/C++ planned | Py/C++ active steps | Py/C++ conflicts | Mean diff | C++ speedup | Parity |
|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| random_topo_seed211_wide_uniform | 3-4-4-3-2 | rolling_horizon_sipp | 36 | 35 | none none | none | 36/36 | 36/36 | 0/0 | 0.000000000000 | 1.953 | True |
| random_topo_seed211_wide_uniform | 3-4-4-3-2 | periodic_replanning_sipp | 36 | 35 | none none | none | 36/36 | 140/140 | 0/0 | 0.000000000000 | 0.417 | True |
| random_topo_seed211_wide_uniform | 3-4-4-3-2 | pibt_active_bag_replay | 36 | 35 | none none | none | 36/36 | 200/200 | 0/0 | 0.000000000000 | 0.667 | True |
| random_topo_seed211_wide_uniform | 3-4-4-3-2 | edge_score_event | 36 | 35 | none none | none | 27/27 | 163/163 | 0/0 | 0.000000000000 | 2.861 | True |
| random_topo_seed211_wide_uniform | 3-4-4-3-2 | fallback_event | 36 | 35 | none none | none | 27/27 | 161/161 | 0/0 | 0.000000000000 | 0.991 | True |
| random_topo_seed223_skewed_bottleneck | 4-3-5-3-2 | rolling_horizon_sipp | 40 | 39 | none none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 40/40 | 40/40 | 0/0 | 0.000000000000 | 0.503 | True |
| random_topo_seed223_skewed_bottleneck | 4-3-5-3-2 | periodic_replanning_sipp | 40 | 39 | none none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 40/40 | 140/140 | 0/0 | 0.000000000000 | 0.431 | True |
| random_topo_seed223_skewed_bottleneck | 4-3-5-3-2 | pibt_active_bag_replay | 40 | 39 | none none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 40/40 | 166/166 | 0/0 | 0.000000000000 | 0.628 | True |
| random_topo_seed223_skewed_bottleneck | 4-3-5-3-2 | edge_score_event | 40 | 39 | none none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 26/26 | 178/178 | 0/0 | 0.000000000000 | 2.411 | True |
| random_topo_seed223_skewed_bottleneck | 4-3-5-3-2 | fallback_event | 40 | 39 | none none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,cap=1,headway=0.25 | 24/24 | 170/170 | 0/0 | 0.000000000000 | 1.082 | True |
| random_topo_seed227_burst_repair | 3-5-3-5-2 | rolling_horizon_sipp | 42 | 42 | none 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 42/42 | 42/42 | 0/0 | 0.000000000000 | 0.462 | True |
| random_topo_seed227_burst_repair | 3-5-3-5-2 | periodic_replanning_sipp | 42 | 42 | none 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 42/42 | 156/156 | 0/0 | 0.000000000000 | 0.364 | True |
| random_topo_seed227_burst_repair | 3-5-3-5-2 | pibt_active_bag_replay | 42 | 42 | none 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 42/42 | 168/168 | 0/0 | 0.000000000000 | 0.686 | True |
| random_topo_seed227_burst_repair | 3-5-3-5-2 | edge_score_event | 42 | 42 | none 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 15/15 | 136/136 | 0/0 | 0.000000000000 | 2.680 | True |
| random_topo_seed227_burst_repair | 3-5-3-5-2 | fallback_event | 42 | 42 | none 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,cap=1,headway=0.0 | 15/15 | 135/135 | 0/0 | 0.000000000000 | 1.249 | True |
| random_topo_seed229_static_alt | 4-4-4-4-3 | rolling_horizon_sipp | 44 | 44 | 10->12 none | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 44/44 | 44/44 | 0/0 | 0.000000000000 | 0.537 | True |
| random_topo_seed229_static_alt | 4-4-4-4-3 | periodic_replanning_sipp | 44 | 44 | 10->12 none | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 44/44 | 162/162 | 0/0 | 0.000000000000 | 0.526 | True |
| random_topo_seed229_static_alt | 4-4-4-4-3 | pibt_active_bag_replay | 44 | 44 | 10->12 none | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 44/44 | 311/311 | 0/0 | 0.000000000000 | 0.681 | True |
| random_topo_seed229_static_alt | 4-4-4-4-3 | edge_score_event | 44 | 44 | 10->12 none | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 23/23 | 190/190 | 0/0 | 0.000000000000 | 2.479 | True |
| random_topo_seed229_static_alt | 4-4-4-4-3 | fallback_event | 44 | 44 | 10->12 none | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,cap=1,headway=0.0 | 21/21 | 191/191 | 0/0 | 0.000000000000 | 1.137 | True |
| random_topo_seed233_shortcut_dense | 5-5-4-5-3 | rolling_horizon_sipp | 48 | 69 | none 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 48/48 | 48/48 | 0/0 | 0.000000000000 | 0.599 | True |
| random_topo_seed233_shortcut_dense | 5-5-4-5-3 | periodic_replanning_sipp | 48 | 69 | none 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 48/48 | 186/186 | 0/0 | 0.000000000000 | 0.472 | True |
| random_topo_seed233_shortcut_dense | 5-5-4-5-3 | pibt_active_bag_replay | 48 | 69 | none 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 48/48 | 191/191 | 0/0 | 0.000000000000 | 0.741 | True |
| random_topo_seed233_shortcut_dense | 5-5-4-5-3 | edge_score_event | 48 | 69 | none 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 25/25 | 149/149 | 0/0 | 0.000000000000 | 2.296 | True |
| random_topo_seed233_shortcut_dense | 5-5-4-5-3 | fallback_event | 48 | 69 | none 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,cap=1,headway=0.25 | 26/26 | 145/145 | 0/0 | 0.000000000000 | 1.108 | True |
| random_topo_seed239_sparse_repair | 3-3-3-3-2 | rolling_horizon_sipp | 34 | 22 | none 3->8@[4.000,18.000) | none | 34/34 | 34/34 | 0/0 | 0.000000000000 | 0.520 | True |
| random_topo_seed239_sparse_repair | 3-3-3-3-2 | periodic_replanning_sipp | 34 | 22 | none 3->8@[4.000,18.000) | none | 34/34 | 133/133 | 0/0 | 0.000000000000 | 0.469 | True |
| random_topo_seed239_sparse_repair | 3-3-3-3-2 | pibt_active_bag_replay | 34 | 22 | none 3->8@[4.000,18.000) | none | 34/34 | 245/245 | 0/0 | 0.000000000000 | 0.624 | True |
| random_topo_seed239_sparse_repair | 3-3-3-3-2 | edge_score_event | 34 | 22 | none 3->8@[4.000,18.000) | none | 8/8 | 99/99 | 0/0 | 0.000000000000 | 2.221 | True |
| random_topo_seed239_sparse_repair | 3-3-3-3-2 | fallback_event | 34 | 22 | none 3->8@[4.000,18.000) | none | 8/8 | 87/87 | 0/0 | 0.000000000000 | 1.030 | True |

## Gate Status

- random topology scenarios: `6` (random_topo_seed211_wide_uniform, random_topo_seed223_skewed_bottleneck, random_topo_seed227_burst_repair, random_topo_seed229_static_alt, random_topo_seed233_shortcut_dense, random_topo_seed239_sparse_repair)
- distinct layer layouts: `6` (3-3-3-3-2, 3-4-4-3-2, 3-5-3-5-2, 4-3-5-3-2, 4-4-4-4-3, 5-5-4-5-3)
- families: `5` (edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, rolling_horizon_sipp)
- matched rows: `30`
- random topology matched Python/C++ summary parity: PASS
- random topology matched post-shield safety: PASS
- median C++ local-call speedup: `0.684x`
- real heldout airport map: not covered

## Remaining Work

- add a separate real heldout airport map when fixture data is available
- expand timing to multi-machine hardware-normalized runs before paper-grade claims
