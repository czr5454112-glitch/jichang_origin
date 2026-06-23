# Phase8 Legacy Event Replay Parity

Date: 2026-06-23

## Scope

This diagnostic compares the Python event-queue replay reference against native C++ event replay on real legacy airport inputs: processed `map2.json` and `inputdata.jsonl` derived from the Java `map2.txt` / `inputdata.txt` files. It checks both aggregate summaries and decision-level traces for EdgeScore-runtime and shortest-safe fallback policies.

Map: `data/processed/maps/map2.json`
Tasks: `data/processed/tasks/inputdata.jsonl`

This is a real legacy-map parity gate on deterministic task windows. It is not a separate heldout airport map claim and not a final throughput benchmark.

## Metrics

| Case | Policy | Offset | Tasks | Faults | Repair windows | Py planned | C++ planned | Py decisions | C++ decisions | Trace rows | Strict parity | First mismatch |
|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|---|
| legacy_first16 | edge_score_event | 0 | 16 | none | none | 16 | 16 | 173 | 173 | 173/173 | True | match:none@ |
| legacy_first16 | fallback_event | 0 | 16 | none | none | 15 | 15 | 168 | 168 | 168/168 | True | match:none@ |
| legacy_offset32_static_fault | edge_score_event | 32 | 16 | 16->17 | none | 12 | 12 | 205 | 205 | 205/205 | True | match:none@ |
| legacy_offset32_static_fault | fallback_event | 32 | 16 | 16->17 | none | 12 | 12 | 193 | 193 | 193/193 | True | match:none@ |
| legacy_offset64_repair_window | edge_score_event | 64 | 16 | none | 28->47@[0.000,12000.000) | 9 | 9 | 150 | 150 | 150/150 | True | match:none@ |
| legacy_offset64_repair_window | fallback_event | 64 | 16 | none | 28->47@[0.000,12000.000) | 8 | 8 | 157 | 157 | 157/157 | True | match:none@ |

CSV: `outputs/tables/phase8_legacy_event_parity.csv`

## Gate Status

- legacy event replay Python/C++ trace parity: PASS
- legacy event replay post-shield safety: PASS
- EdgeScore event parity rows: `3`
- fallback event parity rows: `3`
- real legacy airport map: covered
- separate heldout airport map: not covered
- final throughput scaling: not covered
