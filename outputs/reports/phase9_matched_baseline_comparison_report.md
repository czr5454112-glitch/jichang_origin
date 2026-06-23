# Phase9 Matched Baseline Comparison Diagnostic

Date: 2026-06-23

## Scope

This diagnostic reruns Python and C++ implementations of the main event/baseline families on the same real legacy `map2/inputdata` task windows. It covers no-fault, buffer-capacity, static-fault, and repair-window scenarios that are supported by every included family.

Map: `data/processed/maps/map2.json`
Tasks: `data/processed/tasks/inputdata.jsonl`
CSV: `outputs/tables/phase9_matched_baseline_comparison.csv`

This is a matched diagnostic gate, not a final paper benchmark: timings are single local passes and merge-group variants are handled by the dedicated parity gates.

## Matched Rows

| Scenario | Family | Tasks | Faults | Py planned | C++ planned | Config | Py/C++ active steps | Py/C++ conflicts | Mean diff | C++ speedup | Parity |
|---|---|---:|---|---:|---:|---|---:|---:|---:|---:|---|
| legacy_first16 | rolling_horizon_sipp | 16 | none | 16 | 16 | none | 16/16 | 0/0 | 0.000000 | 5.339 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | 16 | 16 | none | 120/120 | 0/0 | 0.000000 | 0.848 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | 0 | 0 | none | 18599/18599 | 0/0 | 0.000000 | 0.808 | True |
| legacy_first16 | edge_score_event | 16 | none | 16 | 16 | none | 173/173 | 0/0 | 0.000000 | 2.086 | True |
| legacy_first16 | fallback_event | 16 | none | 15 | 15 | none | 168/168 | 0/0 | 0.000000 | 1.002 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | none | 16 | 16 | 28:2;47:2 | 16/16 | 0/0 | 0.000000 | 0.608 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | none | 16 | 16 | 28:2;47:2 | 120/120 | 0/0 | 0.000000 | 0.852 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | none | 0 | 0 | 28:2;47:2 | 18599/18599 | 0/0 | 0.000000 | 0.821 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | none | 16 | 16 | 28:2;47:2 | 173/173 | 0/0 | 0.000000 | 2.126 | True |
| legacy_first16_buffer2 | fallback_event | 16 | none | 15 | 15 | 28:2;47:2 | 168/168 | 0/0 | 0.000000 | 1.066 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | 32 | 32 | none | 32/32 | 0/0 | 0.000000 | 0.830 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | 32 | 32 | none | 248/248 | 0/0 | 0.000000 | 0.733 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | 0 | 0 | none | 41032/41032 | 0/0 | 0.000000 | 0.891 | True |
| legacy_first32 | edge_score_event | 32 | none | 24 | 24 | none | 330/330 | 0/0 | 0.000000 | 2.354 | True |
| legacy_first32 | fallback_event | 32 | none | 25 | 25 | none | 346/346 | 0/0 | 0.000000 | 1.029 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | 16->17 | 16 | 16 | none | 16/16 | 0/0 | 0.000000 | 0.949 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | 16->17 | 16 | 16 | none | 129/129 | 0/0 | 0.000000 | 0.637 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | 16->17 | 0 | 0 | none | 22378/22378 | 0/0 | 0.000000 | 0.820 | True |
| legacy_offset32_static16 | edge_score_event | 16 | 16->17 | 12 | 12 | none | 205/205 | 0/0 | 0.000000 | 2.663 | True |
| legacy_offset32_static16 | fallback_event | 16 | 16->17 | 12 | 12 | none | 193/193 | 0/0 | 0.000000 | 0.928 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | 28->47@[0.000,12000.000) | 32 | 32 | none | 32/32 | 0/0 | 0.000000 | 1.021 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | 28->47@[0.000,12000.000) | 32 | 32 | none | 265/265 | 0/0 | 0.000000 | 0.709 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | 28->47@[0.000,12000.000) | 0 | 0 | none | 50808/50808 | 0/0 | 0.000000 | 0.920 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | 28->47@[0.000,12000.000) | 15 | 15 | none | 323/323 | 0/0 | 0.000000 | 2.184 | True |
| legacy_offset64_repair32 | fallback_event | 32 | 28->47@[0.000,12000.000) | 13 | 13 | none | 321/321 | 0/0 | 0.000000 | 1.217 | True |

## Observations

- `edge_score_event` planned `83/112` matched tasks with exact Python/C++ summary parity.
- `fallback_event` planned `80/112` matched tasks with exact Python/C++ summary parity.
- `periodic_replanning_sipp` planned `112/112` matched tasks with exact Python/C++ summary parity.
- `pibt_active_bag_replay` planned `0/112` matched tasks with exact Python/C++ summary parity.
- `rolling_horizon_sipp` planned `112/112` matched tasks with exact Python/C++ summary parity.

## Gate Status

- scenarios: `5` (legacy_first16, legacy_first16_buffer2, legacy_first32, legacy_offset32_static16, legacy_offset64_repair32)
- families: `5` (edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, rolling_horizon_sipp)
- matched rows: `25`
- Python/C++ summary parity: PASS
- post-shield safety: PASS
- median C++ local-call speedup: `0.928x`
- repair-window common-family comparison: covered
- buffer-capacity common-family comparison: covered
- merge-group common-family comparison: not covered

## Remaining Work

- add merge-group matched rows once every included family accepts the shared config
- replace single local timing with repeated hardware-normalized timing across the matched table
