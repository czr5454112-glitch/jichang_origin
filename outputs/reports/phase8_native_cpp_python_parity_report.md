# Phase8 Native C++ / Python Replay Parity Report

Date: 2026-06-24

## Scope

This diagnostic compares the compact native C++ EdgeScore replay against the existing Python junction environment on identical map2 task windows and fault schedules.

The strict parity gate applies to the loaded EdgeScore runtime policy. The model-unavailable shortest-safe fallback is also checked for strict parity on these small windows; it remains a runtime contingency rather than the learned-policy claim.

## Metrics

| Case | Policy | Faults | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Strict parity | Safety |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| first8 | edge_score_runtime | none | 8 | 8 | 78 | 78 | 0.000000000000 | 0 | 0 | True | True |
| first8 | shortest_safe_fallback | none | 8 | 8 | 73 | 73 | 0.000000000000 | 0 | 0 | True | True |
| first16 | edge_score_runtime | none | 16 | 16 | 173 | 173 | 0.000000000000 | 0 | 0 | True | True |
| first16 | shortest_safe_fallback | none | 16 | 16 | 198 | 198 | 0.000000000000 | 0 | 0 | True | True |
| fault_alt_route_first8 | edge_score_runtime | 16->17 | 8 | 8 | 74 | 74 | 0.000000000000 | 0 | 0 | True | True |
| fault_alt_route_first8 | shortest_safe_fallback | 16->17 | 8 | 8 | 73 | 73 | 0.000000000000 | 0 | 0 | True | True |
| fault_goal_exit_first8 | edge_score_runtime | 28->47 | 8 | 8 | 186 | 186 | 0.000000000000 | 0 | 0 | True | True |
| fault_goal_exit_first8 | shortest_safe_fallback | 28->47 | 8 | 8 | 155 | 155 | 0.000000000000 | 0 | 0 | True | True |

CSV: `outputs/tables/phase8_native_cpp_python_parity.csv`

## Gate Status

- EdgeScore native C++ vs Python strict replay parity: PASS
- fallback safety diagnostic: PASS
- fallback strict replay parity: PASS
- fallback strict parity rows: `4/4`
- native event-scheduler parity: covered by `outputs/reports/phase8_native_cpp_event_parity_report.md`
- real legacy event-scheduler parity: covered by `outputs/reports/phase8_legacy_event_parity_report.md`

## Remaining Work

- keep fallback parity covered when expanding to repair events, randomized density, and heldout maps
- expand parity to larger windows, repair events, randomized density, and heldout maps
- keep compact and event-scheduler parity aligned when adding new runtime policy formats
