# Phase9 Matched Baseline Comparison Diagnostic

Date: 2026-06-24

## Scope

This diagnostic reruns Python and C++ implementations of the main event/baseline families on the same real legacy `map2/inputdata` task windows. It covers no-fault, buffer-capacity, static-fault, repair-window, and merge-group scenarios that are supported by every included family.

Map: `data/processed/maps/map2.json`
Tasks: `data/processed/tasks/inputdata.jsonl`
CSV: `outputs/tables/phase9_matched_baseline_comparison.csv`

This is a matched diagnostic gate, not a final paper benchmark: timings are single local passes intended to verify common-scenario parity. Repeated matched timing with hardware metadata is tracked separately in `outputs/reports/phase9_matched_runtime_scaling_report.md`.

## Matched Rows

| Scenario | Family | Tasks | Faults | Py planned | C++ planned | Config | Py/C++ active steps | Py/C++ conflicts | Mean diff | C++ speedup | Parity |
|---|---|---:|---|---:|---:|---|---:|---:|---:|---:|---|
| legacy_first16 | rolling_horizon_sipp | 16 | none | 16 | 16 | none | 16/16 | 0/0 | 0.000000 | 1.878 | True |
| legacy_first16 | periodic_replanning_sipp | 16 | none | 16 | 16 | none | 120/120 | 0/0 | 0.000000 | 0.298 | True |
| legacy_first16 | pibt_active_bag_replay | 16 | none | 0 | 0 | none | 18599/18599 | 0/0 | 0.000000 | 0.699 | True |
| legacy_first16 | edge_score_event | 16 | none | 16 | 16 | none | 173/173 | 0/0 | 0.000000 | 1.980 | True |
| legacy_first16 | fallback_event | 16 | none | 15 | 15 | none | 168/168 | 0/0 | 0.000000 | 1.043 | True |
| legacy_first16_buffer2 | rolling_horizon_sipp | 16 | none | 16 | 16 | nodes=28:2;47:2 | 16/16 | 0/0 | 0.000000 | 0.209 | True |
| legacy_first16_buffer2 | periodic_replanning_sipp | 16 | none | 16 | 16 | nodes=28:2;47:2 | 120/120 | 0/0 | 0.000000 | 0.265 | True |
| legacy_first16_buffer2 | pibt_active_bag_replay | 16 | none | 0 | 0 | nodes=28:2;47:2 | 18599/18599 | 0/0 | 0.000000 | 0.743 | True |
| legacy_first16_buffer2 | edge_score_event | 16 | none | 16 | 16 | nodes=28:2;47:2 | 173/173 | 0/0 | 0.000000 | 1.872 | True |
| legacy_first16_buffer2 | fallback_event | 16 | none | 15 | 15 | nodes=28:2;47:2 | 168/168 | 0/0 | 0.000000 | 0.923 | True |
| legacy_first32 | rolling_horizon_sipp | 32 | none | 32 | 32 | none | 32/32 | 0/0 | 0.000000 | 0.291 | True |
| legacy_first32 | periodic_replanning_sipp | 32 | none | 32 | 32 | none | 248/248 | 0/0 | 0.000000 | 0.351 | True |
| legacy_first32 | pibt_active_bag_replay | 32 | none | 0 | 0 | none | 41032/41032 | 0/0 | 0.000000 | 0.802 | True |
| legacy_first32 | edge_score_event | 32 | none | 24 | 24 | none | 330/330 | 0/0 | 0.000000 | 2.971 | True |
| legacy_first32 | fallback_event | 32 | none | 25 | 25 | none | 346/346 | 0/0 | 0.000000 | 0.986 | True |
| legacy_offset32_static16 | rolling_horizon_sipp | 16 | 16->17 | 16 | 16 | none | 16/16 | 0/0 | 0.000000 | 0.306 | True |
| legacy_offset32_static16 | periodic_replanning_sipp | 16 | 16->17 | 16 | 16 | none | 129/129 | 0/0 | 0.000000 | 0.255 | True |
| legacy_offset32_static16 | pibt_active_bag_replay | 16 | 16->17 | 0 | 0 | none | 22378/22378 | 0/0 | 0.000000 | 0.795 | True |
| legacy_offset32_static16 | edge_score_event | 16 | 16->17 | 12 | 12 | none | 205/205 | 0/0 | 0.000000 | 2.379 | True |
| legacy_offset32_static16 | fallback_event | 16 | 16->17 | 12 | 12 | none | 193/193 | 0/0 | 0.000000 | 1.173 | True |
| legacy_offset64_repair32 | rolling_horizon_sipp | 32 | 28->47@[0.000,12000.000) | 32 | 32 | none | 32/32 | 0/0 | 0.000000 | 0.361 | True |
| legacy_offset64_repair32 | periodic_replanning_sipp | 32 | 28->47@[0.000,12000.000) | 32 | 32 | none | 265/265 | 0/0 | 0.000000 | 0.337 | True |
| legacy_offset64_repair32 | pibt_active_bag_replay | 32 | 28->47@[0.000,12000.000) | 0 | 0 | none | 50808/50808 | 0/0 | 0.000000 | 0.829 | True |
| legacy_offset64_repair32 | edge_score_event | 32 | 28->47@[0.000,12000.000) | 15 | 15 | none | 323/323 | 0/0 | 0.000000 | 2.468 | True |
| legacy_offset64_repair32 | fallback_event | 32 | 28->47@[0.000,12000.000) | 13 | 13 | none | 321/321 | 0/0 | 0.000000 | 1.183 | True |
| legacy_offset64_merge32 | rolling_horizon_sipp | 32 | none | 32 | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 32/32 | 0/0 | 0.000000 | 0.272 | True |
| legacy_offset64_merge32 | periodic_replanning_sipp | 32 | none | 32 | 32 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 260/260 | 0/0 | 0.000000 | 0.342 | True |
| legacy_offset64_merge32 | pibt_active_bag_replay | 32 | none | 0 | 0 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 51876/51876 | 0/0 | 0.000000 | 0.691 | True |
| legacy_offset64_merge32 | edge_score_event | 32 | none | 14 | 14 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 332/332 | 0/0 | 0.000000 | 2.626 | True |
| legacy_offset64_merge32 | fallback_event | 32 | none | 13 | 13 | merge=13->23:9;18->22:9,cap=1,headway=0.0 | 334/334 | 0/0 | 0.000000 | 1.265 | True |

## Observations

- `edge_score_event` planned `97/144` matched tasks with exact Python/C++ summary parity.
- `fallback_event` planned `93/144` matched tasks with exact Python/C++ summary parity.
- `periodic_replanning_sipp` planned `144/144` matched tasks with exact Python/C++ summary parity.
- `pibt_active_bag_replay` planned `0/144` matched tasks with exact Python/C++ summary parity.
- `rolling_horizon_sipp` planned `144/144` matched tasks with exact Python/C++ summary parity.

## Gate Status

- scenarios: `6` (legacy_first16, legacy_first16_buffer2, legacy_first32, legacy_offset32_static16, legacy_offset64_merge32, legacy_offset64_repair32)
- families: `5` (edge_score_event, fallback_event, periodic_replanning_sipp, pibt_active_bag_replay, rolling_horizon_sipp)
- matched rows: `30`
- Python/C++ summary parity: PASS
- post-shield safety: PASS
- median C++ local-call speedup: `0.799x`
- repair-window common-family comparison: covered
- buffer-capacity common-family comparison: covered
- merge-group common-family comparison: covered

## Remaining Work

- expand matched rows to separate real heldout airport maps when fixture data is available
