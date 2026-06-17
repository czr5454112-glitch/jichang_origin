# Phase8 Native C++ Event Trace Diagnostic

Date: 2026-06-17

## Scope

This diagnostic audits the native C++ event-queue replay trace on the persisted synthetic manifest. It checks event-scheduler invariants directly: chronological decision events, per-task ready-time monotonicity, contiguous decision ordinals, post-shield action safety, and complete planned/unplanned accounting.

Manifest: `data/processed/phase8/phase8_synthetic_replay_cases.json`

This is an event-trace audit, not a strict compact replay parity claim. Compact replay routes one task to completion before the next task, while this scheduler interleaves active bags by event time.

## Metrics

| Case | Policy | Tasks | Planned | Unplanned | Decisions | Trace rows | Conflicts | Last ready | Max task decisions | Pass | First failure |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| synthetic_seed7_medium_repair | edge_score_event | 18 | 18 | 0 | 55 | 55 | 0 | 63.369310114611 | 4 | True | none |
| synthetic_seed7_medium_repair | fallback_event | 18 | 18 | 0 | 55 | 55 | 0 | 63.369310114611 | 4 | True | none |
| synthetic_seed11_dense_multi_repair | edge_score_event | 24 | 16 | 8 | 112 | 112 | 0 | 48.683572298849 | 13 | True | none |
| synthetic_seed11_dense_multi_repair | fallback_event | 24 | 16 | 8 | 112 | 112 | 0 | 48.683572298849 | 13 | True | none |
| synthetic_seed17_static_plus_repair | edge_score_event | 20 | 12 | 8 | 97 | 97 | 0 | 56.525476928365 | 8 | True | none |
| synthetic_seed17_static_plus_repair | fallback_event | 20 | 12 | 8 | 97 | 97 | 0 | 56.525476928365 | 8 | True | none |
| synthetic_seed23_repeated_repair | edge_score_event | 22 | 20 | 2 | 85 | 85 | 0 | 49.045341958722 | 6 | True | none |
| synthetic_seed23_repeated_repair | fallback_event | 22 | 19 | 3 | 93 | 93 | 0 | 49.045341958722 | 7 | True | none |

CSV: `outputs/tables/phase8_native_cpp_event_trace_diagnostic.csv`

## Gate Status

- event trace invariants: PASS
- EdgeScore and fallback event traces covered: PASS
- persisted synthetic manifest covered: PASS
- Python event-scheduler trace parity: covered by `phase8_native_cpp_event_parity_report.md`
- final paper-grade scheduler throughput: not covered

## Remaining Work

- scale this diagnostic over larger persisted manifests
- carry the event trace audit into Phase9 baseline and policy comparisons
