# Phase9 Event Runtime Scaling Diagnostic

Date: 2026-06-23

## Scope

This diagnostic measures Python event replay against native C++ event replay on real legacy `map2/inputdata` task windows. It records scheduler runtime, decision throughput, task throughput, safety, and summary parity for EdgeScore-runtime and shortest-safe fallback policies.

Map: `data/processed/maps/map2.json`
Tasks: `data/processed/tasks/inputdata.jsonl`

This is an early Phase9 runtime-scaling gate. It is not a final paper benchmark: results are single-run timings on the local workstation and should be expanded before making claims.

## Metrics

| Case | Policy | Tasks | Py decisions | C++ decisions | Py seconds | C++ seconds | Py decisions/s | C++ decisions/s | C++ speedup | Parity | First mismatch |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| legacy_first16 | edge_score_event | 16 | 173 | 173 | 0.085315 | 0.040108 | 2027.78 | 4313.40 | 2.127 | True | match:none |
| legacy_first16 | fallback_event | 16 | 168 | 168 | 0.032932 | 0.031489 | 5101.47 | 5335.25 | 1.046 | True | match:none |
| legacy_first32 | edge_score_event | 32 | 330 | 330 | 0.172952 | 0.065540 | 1908.05 | 5035.11 | 2.639 | True | match:none |
| legacy_first32 | fallback_event | 32 | 346 | 346 | 0.071672 | 0.059893 | 4827.57 | 5776.94 | 1.197 | True | match:none |
| legacy_first64 | edge_score_event | 64 | 695 | 695 | 0.369978 | 0.138681 | 1878.49 | 5011.50 | 2.668 | True | match:none |
| legacy_first64 | fallback_event | 64 | 721 | 721 | 0.158697 | 0.120471 | 4543.24 | 5984.82 | 1.317 | True | match:none |
| legacy_offset64_repair32 | edge_score_event | 32 | 323 | 323 | 0.176242 | 0.056451 | 1832.71 | 5721.82 | 3.122 | True | match:none |
| legacy_offset64_repair32 | fallback_event | 32 | 321 | 321 | 0.070364 | 0.050215 | 4562.01 | 6392.50 | 1.401 | True | match:none |

CSV: `outputs/tables/phase9_event_runtime_scaling.csv`

## Gate Status

- event runtime summary parity: PASS
- event runtime post-shield safety: PASS
- EdgeScore runtime rows: `4`
- fallback runtime rows: `4`
- median C++ decision-throughput speedup: `1.764x`
- single-run local timing only: YES
- final paper-grade throughput claim: not covered

## Remaining Work

- add repeated-run timing with hardware metadata and confidence intervals
- scale to larger persisted manifests and separate heldout maps
- compare against Phase2 baseline families in a unified Phase9 table
