# Phase9 Matched Baseline Comparison Diagnostic

Date: 2026-06-23

## Scope

This diagnostic reruns Python and C++ implementations of the main event/baseline families on the same real legacy `map2/inputdata` task windows. It covers no-fault and static-fault scenarios that are supported by every included family.

Map: `data/processed/maps/map2.json`
Tasks: `data/processed/tasks/inputdata.jsonl`
CSV: `outputs/tables/phase9_matched_baseline_comparison.csv`

This is a matched diagnostic gate, not a final paper benchmark: timings are single local passes and repair-window/merge-buffer variants are handled by the dedicated parity gates.

## Matched Rows

| Scenario | Family | Tasks | Faults | Py planned | C++ planned | Py/C++ active steps | Py/C++ conflicts | Mean diff | C++ speedup | Parity |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| legacy_first16 | rolling_horizon_sipp | 16 | none | 16 | 16 | 16/16 | 0/0 | 0.000000 | 5.298 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | 16 | 16 | 120/120 | 0/0 | 0.000000 | 0.737 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | 0 | 0 | 18599/18599 | 0/0 | 0.000000 | 0.887 | True |
| legacy_first16 | edge_score_event | 16 | none | 16 | 16 | 173/173 | 0/0 | 0.000000 | 2.319 | True |
| legacy_first16 | fallback_event | 16 | none | 15 | 15 | 168/168 | 0/0 | 0.000000 | 1.042 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | 32 | 32 | 32/32 | 0/0 | 0.000000 | 0.969 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | 32 | 32 | 248/248 | 0/0 | 0.000000 | 0.940 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | 0 | 0 | 41032/41032 | 0/0 | 0.000000 | 0.908 | True |
| legacy_first32 | edge_score_event | 32 | none | 24 | 24 | 330/330 | 0/0 | 0.000000 | 2.395 | True |
| legacy_first32 | fallback_event | 32 | none | 25 | 25 | 346/346 | 0/0 | 0.000000 | 1.184 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | 16->17 | 16 | 16 | 16/16 | 0/0 | 0.000000 | 0.875 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | 16->17 | 16 | 16 | 129/129 | 0/0 | 0.000000 | 0.855 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | 16->17 | 0 | 0 | 22378/22378 | 0/0 | 0.000000 | 0.873 | True |
| legacy_offset32_static16 | edge_score_event | 16 | 16->17 | 12 | 12 | 205/205 | 0/0 | 0.000000 | 2.564 | True |
| legacy_offset32_static16 | fallback_event | 16 | 16->17 | 12 | 12 | 193/193 | 0/0 | 0.000000 | 1.146 | True |

## Observations

- `edge_score_event` planned `52/64` matched tasks with exact Python/C++ summary parity.
- `fallback_event` planned `52/64` matched tasks with exact Python/C++ summary parity.
- `periodic_replanning_sipp` planned `64/64` matched tasks with exact Python/C++ summary parity.
- `pibt_active_bag_replay` planned `0/64` matched tasks with exact Python/C++ summary parity.
- `rolling_horizon_sipp` planned `64/64` matched tasks with exact Python/C++ summary parity.

## Gate Status

- scenarios: `3` (legacy_first16, legacy_first32, legacy_offset32_static16)
- families: `5` (edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, rolling_horizon_sipp)
- matched rows: `15`
- Python/C++ summary parity: PASS
- post-shield safety: PASS
- median C++ local-call speedup: `0.969x`
- repair-window common-family comparison: not covered
- merge/buffer common-family comparison: not covered

## Remaining Work

- add repair-window rows for families that support them or extend rolling-horizon semantics
- add merge/buffer matched rows once every included family accepts the shared config
- replace single local timing with repeated hardware-normalized timing across the matched table
