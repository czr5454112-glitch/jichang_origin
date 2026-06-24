# Phase9 Synthetic Matched Baseline Comparison Diagnostic

Date: 2026-06-24

## Scope

This diagnostic reruns Python and C++ implementations of the main event/baseline families on fixed-seed synthetic ICS-like maps from the persisted Phase8 manifest. The rows vary density, branch structure, static faults, repair windows, buffer capacity, and merge-group capacity.

Manifest: `data/processed/phase8/phase8_synthetic_replay_cases.json`
CSV: `outputs/tables/phase9_synthetic_matched_baseline_comparison.csv`

This is heldout-like synthetic-map coverage, not a separate real airport-map claim.

## Matched Rows

| Scenario | Family | Tasks | Edges | Faults | Config | Py/C++ planned | Py/C++ active steps | Py/C++ conflicts | Mean diff | C++ speedup | Parity |
|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| synthetic_seed7_medium_repair | rolling_horizon_sipp | 18 | 20 | none 4->8@[4.000,18.000) | none | 18/18 | 18/18 | 0/0 | 0.000000000000 | 7.206 | True |
| synthetic_seed7_medium_repair | periodic_replanning_sipp | 18 | 20 | none 4->8@[4.000,18.000) | none | 18/18 | 54/54 | 0/0 | 0.000000000000 | 0.455 | True |
| synthetic_seed7_medium_repair | pibt_active_bag_replay | 18 | 20 | none 4->8@[4.000,18.000) | none | 18/18 | 56/56 | 0/0 | 0.000000000000 | 0.572 | True |
| synthetic_seed7_medium_repair | edge_score_event | 18 | 20 | none 4->8@[4.000,18.000) | none | 18/18 | 55/55 | 0/0 | 0.000000000000 | 2.835 | True |
| synthetic_seed7_medium_repair | fallback_event | 18 | 20 | none 4->8@[4.000,18.000) | none | 18/18 | 55/55 | 0/0 | 0.000000000000 | 0.605 | True |
| synthetic_seed11_dense_multi_repair | rolling_horizon_sipp | 24 | 18 | none 7->9@[5.000,16.000);8->9@[10.000,22.000) | none | 24/24 | 24/24 | 0/0 | 0.000000000000 | 0.639 | True |
| synthetic_seed11_dense_multi_repair | periodic_replanning_sipp | 24 | 18 | none 7->9@[5.000,16.000);8->9@[10.000,22.000) | none | 24/24 | 87/87 | 0/0 | 0.000000000000 | 0.565 | True |
| synthetic_seed11_dense_multi_repair | pibt_active_bag_replay | 24 | 18 | none 7->9@[5.000,16.000);8->9@[10.000,22.000) | none | 24/24 | 292/292 | 0/0 | 0.000000000000 | 0.544 | True |
| synthetic_seed11_dense_multi_repair | edge_score_event | 24 | 18 | none 7->9@[5.000,16.000);8->9@[10.000,22.000) | none | 15/15 | 125/125 | 0/0 | 0.000000000000 | 1.848 | True |
| synthetic_seed11_dense_multi_repair | fallback_event | 24 | 18 | none 7->9@[5.000,16.000);8->9@[10.000,22.000) | none | 15/15 | 125/125 | 0/0 | 0.000000000000 | 0.804 | True |
| synthetic_seed17_static_plus_repair | rolling_horizon_sipp | 20 | 17 | 4->7 5->8@[0.000,14.000) | none | 20/20 | 20/20 | 0/0 | 0.000000000000 | 0.685 | True |
| synthetic_seed17_static_plus_repair | periodic_replanning_sipp | 20 | 17 | 4->7 5->8@[0.000,14.000) | none | 20/20 | 76/76 | 0/0 | 0.000000000000 | 0.454 | True |
| synthetic_seed17_static_plus_repair | pibt_active_bag_replay | 20 | 17 | 4->7 5->8@[0.000,14.000) | none | 20/20 | 324/324 | 0/0 | 0.000000000000 | 0.550 | True |
| synthetic_seed17_static_plus_repair | edge_score_event | 20 | 17 | 4->7 5->8@[0.000,14.000) | none | 12/12 | 97/97 | 0/0 | 0.000000000000 | 2.100 | True |
| synthetic_seed17_static_plus_repair | fallback_event | 20 | 17 | 4->7 5->8@[0.000,14.000) | none | 12/12 | 97/97 | 0/0 | 0.000000000000 | 0.753 | True |
| synthetic_seed23_repeated_repair | rolling_horizon_sipp | 22 | 17 | none 4->8@[3.000,8.000);4->8@[14.000,21.000);8->9@[9.000,15.000) | none | 22/22 | 22/22 | 0/0 | 0.000000000000 | 0.529 | True |
| synthetic_seed23_repeated_repair | periodic_replanning_sipp | 22 | 17 | none 4->8@[3.000,8.000);4->8@[14.000,21.000);8->9@[9.000,15.000) | none | 22/22 | 74/74 | 0/0 | 0.000000000000 | 0.380 | True |
| synthetic_seed23_repeated_repair | pibt_active_bag_replay | 22 | 17 | none 4->8@[3.000,8.000);4->8@[14.000,21.000);8->9@[9.000,15.000) | none | 22/22 | 187/187 | 0/0 | 0.000000000000 | 0.542 | True |
| synthetic_seed23_repeated_repair | edge_score_event | 22 | 17 | none 4->8@[3.000,8.000);4->8@[14.000,21.000);8->9@[9.000,15.000) | none | 20/20 | 85/85 | 0/0 | 0.000000000000 | 1.697 | True |
| synthetic_seed23_repeated_repair | fallback_event | 22 | 17 | none 4->8@[3.000,8.000);4->8@[14.000,21.000);8->9@[9.000,15.000) | none | 19/19 | 93/93 | 0/0 | 0.000000000000 | 0.693 | True |
| synthetic_seed31_merge_buffer | rolling_horizon_sipp | 26 | 20 | none 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 26/26 | 26/26 | 0/0 | 0.000000000000 | 0.472 | True |
| synthetic_seed31_merge_buffer | periodic_replanning_sipp | 26 | 20 | none 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 26/26 | 81/81 | 0/0 | 0.000000000000 | 0.503 | True |
| synthetic_seed31_merge_buffer | pibt_active_bag_replay | 26 | 20 | none 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 26/26 | 123/123 | 0/0 | 0.000000000000 | 0.587 | True |
| synthetic_seed31_merge_buffer | edge_score_event | 26 | 20 | none 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 22/22 | 109/109 | 0/0 | 0.000000000000 | 1.827 | True |
| synthetic_seed31_merge_buffer | fallback_event | 26 | 20 | none 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 22/22 | 109/109 | 0/0 | 0.000000000000 | 0.864 | True |

## Gate Status

- synthetic scenarios: `5` (synthetic_seed11_dense_multi_repair, synthetic_seed17_static_plus_repair, synthetic_seed23_repeated_repair, synthetic_seed31_merge_buffer, synthetic_seed7_medium_repair)
- families: `5` (edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, rolling_horizon_sipp)
- matched rows: `25`
- synthetic matched Python/C++ summary parity: PASS
- synthetic matched non-PIBT post-shield safety: PASS
- synthetic matched all-family post-shield safety: PASS
- PIBT active-bag dense stress conflict rows: `0`
- median C++ local-call speedup: `0.605x`
- persisted synthetic manifest: PASS
- dense-PIBT stress rows are safety-clean: PASS
- real heldout airport map: not covered

## Remaining Work

- add a separate real heldout airport map when fixture data is available
- expand randomized density/fault seeds before paper-grade claims
