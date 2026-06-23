# Phase8 Native C++ Event Scheduler Smoke

Date: 2026-06-23

## Scope

This smoke runs the first native C++ event-queue replay path. Tasks enter the event queue by `pass_time`; each bag schedules decision events at its local ready time after start-node service, hold, edge traversal, or node service. The scheduler reuses the C++ EdgeScore runtime model, `JunctionShield`, node/edge reservations, and repair-window fault handling.

Manifest: `data/processed/phase8/phase8_synthetic_replay_cases.json`

This is a high-throughput scheduler integration smoke, not a final Python parity claim. The compact replay routes one task to completion before the next task, while this event scheduler interleaves active bags chronologically, so aggregate planned counts can differ on dense cases.

## Metrics

| Case | Policy | Tasks | Planned | Unplanned | Decisions | Conflicts | Mean travel | Decisions/s | Compact planned | Compact decisions | Accounted | Safety |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| synthetic_seed7_medium_repair | edge_score_event | 18 | 18 | 0 | 55 | 0 | 9.152747331724 | 7150.29 | 18 | 55 | True | True |
| synthetic_seed7_medium_repair | fallback_event | 18 | 18 | 0 | 55 | 0 | 9.152747331724 | 7035.14 | 18 | 55 | True | True |
| synthetic_seed11_dense_multi_repair | edge_score_event | 24 | 16 | 8 | 112 | 0 | 14.121867493002 | 10454.30 | 18 | 140 | True | True |
| synthetic_seed11_dense_multi_repair | fallback_event | 24 | 16 | 8 | 112 | 0 | 14.121867493002 | 12174.84 | 18 | 140 | True | True |
| synthetic_seed17_static_plus_repair | edge_score_event | 20 | 12 | 8 | 97 | 0 | 16.972989032025 | 10350.97 | 14 | 247 | True | True |
| synthetic_seed17_static_plus_repair | fallback_event | 20 | 12 | 8 | 97 | 0 | 16.972989032025 | 10984.16 | 14 | 247 | True | True |
| synthetic_seed23_repeated_repair | edge_score_event | 22 | 20 | 2 | 85 | 0 | 12.984904736897 | 10311.78 | 20 | 128 | True | True |
| synthetic_seed23_repeated_repair | fallback_event | 22 | 19 | 3 | 93 | 0 | 13.729371734283 | 11567.02 | 20 | 128 | True | True |
| synthetic_seed31_merge_buffer | edge_score_event | 26 | 22 | 4 | 104 | 0 | 11.646110896340 | 9434.82 | 25 | 185 | True | True |
| synthetic_seed31_merge_buffer | fallback_event | 26 | 22 | 4 | 104 | 0 | 11.646110896340 | 11644.70 | 25 | 185 | True | True |

CSV: `outputs/tables/phase8_native_cpp_event_scheduler.csv`

## Gate Status

- event scheduler accounted all configured tasks: PASS
- event scheduler post-shield safety: PASS
- EdgeScore event rows: `5`
- fallback event rows: `5`
- compact-vs-event strict metric parity: not expected
- Python/C++ event trace parity: covered by `phase8_native_cpp_event_parity_report.md`
- final paper-grade scheduler throughput: not covered

## Remaining Work

- add larger manifest sweeps and runtime scaling measurements
- carry this scheduler path into Phase9 baseline and policy comparisons
