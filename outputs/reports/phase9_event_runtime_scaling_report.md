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
| legacy_first16 | edge_score_event | 16 | 173 | 173 | 0.092733+/-0.004473 | 0.039193+/-0.001463 | 1865.58 | 4414.06 | 2.366 | True | match:none |
| legacy_first16 | fallback_event | 16 | 168 | 168 | 0.041548+/-0.003065 | 0.035081+/-0.001924 | 4043.47 | 4788.91 | 1.184 | True | match:none |
| legacy_first32 | edge_score_event | 32 | 330 | 330 | 0.184321+/-0.005907 | 0.073843+/-0.001747 | 1790.36 | 4468.93 | 2.496 | True | match:none |
| legacy_first32 | fallback_event | 32 | 346 | 346 | 0.073674+/-0.002229 | 0.065392+/-0.002655 | 4696.39 | 5291.13 | 1.127 | True | match:none |
| legacy_first64 | edge_score_event | 64 | 695 | 695 | 0.391772+/-0.011774 | 0.146148+/-0.005271 | 1773.99 | 4755.45 | 2.681 | True | match:none |
| legacy_first64 | fallback_event | 64 | 721 | 721 | 0.164165+/-0.007623 | 0.128189+/-0.006450 | 4391.93 | 5624.49 | 1.281 | True | match:none |
| legacy_offset64_repair32 | edge_score_event | 32 | 323 | 323 | 0.172698+/-0.005626 | 0.060607+/-0.001695 | 1870.32 | 5329.46 | 2.849 | True | match:none |
| legacy_offset64_repair32 | fallback_event | 32 | 321 | 321 | 0.067367+/-0.001629 | 0.055447+/-0.002069 | 4764.91 | 5789.31 | 1.215 | True | match:none |

CSV: `outputs/tables/phase9_event_runtime_scaling.csv`

## Gate Status

- event runtime summary parity: PASS
- event runtime post-shield safety: PASS
- EdgeScore runtime rows: `4`
- fallback runtime rows: `4`
- median C++ decision-throughput speedup: `1.823x`
- repeated local timing with environment metadata: YES
- final paper-grade throughput claim: not covered

## Remaining Work

- add more task windows and hardware-normalized runs
- scale to larger persisted manifests and separate heldout maps
- extend the unified Phase9 comparison with matched baseline-family runtime rows
