# Phase9 Event Runtime Scaling Diagnostic

Date: 2026-06-23

## Scope

This diagnostic measures Python event replay against native C++ event replay on real legacy `map2/inputdata` task windows. It records scheduler runtime, decision throughput, task throughput, safety, and summary parity for EdgeScore-runtime and shortest-safe fallback policies.

Map: `data/processed/maps/map2.json`
Tasks: `data/processed/tasks/inputdata.jsonl`

This is an early Phase9 runtime-scaling gate. It is not a final paper benchmark: results are repeated local timings on one workstation and should be expanded before making claims.

## Environment

- repeats per row: `5`
- platform: `Windows-10-10.0.26200-SP0`
- machine: `AMD64`
- processor: `Intel64 Family 6 Model 170 Stepping 4, GenuineIntel`
- CPU count: `22`
- Python: `3.11.9`
- timer: `perf_counter` resolution `1e-07` seconds

## Metrics

| Case | Policy | Tasks | Py decisions | C++ decisions | Py seconds mean+/-95% CI | C++ seconds mean+/-95% CI | Py decisions/s | C++ decisions/s | C++ speedup | Parity | First mismatch |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| legacy_first16 | edge_score_event | 16 | 173 | 173 | 0.117239+/-0.019628 | 0.053470+/-0.010734 | 1475.61 | 3235.44 | 2.193 | True | match:none |
| legacy_first16 | fallback_event | 16 | 168 | 168 | 0.036353+/-0.003649 | 0.033083+/-0.002604 | 4621.42 | 5078.19 | 1.099 | True | match:none |
| legacy_first32 | edge_score_event | 32 | 330 | 330 | 0.171708+/-0.001232 | 0.069652+/-0.004564 | 1921.86 | 4737.87 | 2.465 | True | match:none |
| legacy_first32 | fallback_event | 32 | 346 | 346 | 0.072240+/-0.002306 | 0.062534+/-0.003178 | 4789.57 | 5532.95 | 1.155 | True | match:none |
| legacy_first64 | edge_score_event | 64 | 695 | 695 | 0.362827+/-0.005364 | 0.131052+/-0.001225 | 1915.51 | 5303.25 | 2.769 | True | match:none |
| legacy_first64 | fallback_event | 64 | 721 | 721 | 0.153201+/-0.004330 | 0.123116+/-0.003912 | 4706.23 | 5856.27 | 1.244 | True | match:none |
| legacy_offset64_repair32 | edge_score_event | 32 | 323 | 323 | 0.167784+/-0.001062 | 0.059014+/-0.002195 | 1925.09 | 5473.24 | 2.843 | True | match:none |
| legacy_offset64_repair32 | fallback_event | 32 | 321 | 321 | 0.067141+/-0.001616 | 0.053008+/-0.001761 | 4780.99 | 6055.67 | 1.267 | True | match:none |

CSV: `outputs/tables/phase9_event_runtime_scaling.csv`

## Gate Status

- event runtime summary parity: PASS
- event runtime post-shield safety: PASS
- EdgeScore runtime rows: `4`
- fallback runtime rows: `4`
- median C++ decision-throughput speedup: `1.730x`
- repeated local timing with environment metadata: YES
- final paper-grade throughput claim: not covered

## Remaining Work

- add more task windows and hardware-normalized runs
- scale to larger persisted manifests and separate heldout maps
- compare against Phase2 baseline families in a unified Phase9 table
