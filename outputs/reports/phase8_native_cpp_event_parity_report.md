# Phase8 Native C++ Event Scheduler Parity

Date: 2026-06-17

## Scope

This diagnostic compares the Python event-queue replay reference against native C++ event replay on the persisted synthetic manifest. It checks both aggregate summaries and decision-level traces for EdgeScore-runtime and shortest-safe fallback policies.

Manifest: `data/processed/phase8/phase8_synthetic_replay_cases.json`

This validates event-scheduler Python/C++ semantics on synthetic heldout-like fixtures. It is still not a real-airport heldout map or final paper-grade throughput claim.

## Metrics

| Case | Policy | Py planned | C++ planned | Py decisions | C++ decisions | Mean diff | Trace rows | Strict parity | First mismatch |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| synthetic_seed7_medium_repair | edge_score_event | 18 | 18 | 55 | 55 | 0.000000000000 | 55/55 | True | match:none@ |
| synthetic_seed7_medium_repair | fallback_event | 18 | 18 | 55 | 55 | 0.000000000000 | 55/55 | True | match:none@ |
| synthetic_seed11_dense_multi_repair | edge_score_event | 16 | 16 | 112 | 112 | 0.000000000000 | 112/112 | True | match:none@ |
| synthetic_seed11_dense_multi_repair | fallback_event | 16 | 16 | 112 | 112 | 0.000000000000 | 112/112 | True | match:none@ |
| synthetic_seed17_static_plus_repair | edge_score_event | 12 | 12 | 97 | 97 | 0.000000000000 | 97/97 | True | match:none@ |
| synthetic_seed17_static_plus_repair | fallback_event | 12 | 12 | 97 | 97 | 0.000000000000 | 97/97 | True | match:none@ |
| synthetic_seed23_repeated_repair | edge_score_event | 20 | 20 | 85 | 85 | 0.000000000000 | 85/85 | True | match:none@ |
| synthetic_seed23_repeated_repair | fallback_event | 19 | 19 | 93 | 93 | 0.000000000000 | 93/93 | True | match:none@ |

CSV: `outputs/tables/phase8_native_cpp_event_parity.csv`

## Gate Status

- event scheduler Python/C++ trace parity: PASS
- event scheduler post-shield safety: PASS
- EdgeScore event parity rows: `4`
- fallback event parity rows: `4`
- real heldout airport map: not covered
- final throughput scaling: not covered
