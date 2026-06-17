# Phase8 Native C++ / Python Replay Parity Report

Date: 2026-06-17

## Scope

This diagnostic compares the compact native C++ EdgeScore replay against the existing Python junction environment on identical map2 task windows and fault schedules.

The strict parity gate applies to the loaded EdgeScore runtime policy. The model-unavailable shortest-safe fallback is reported as a safety diagnostic because the compact C++ fallback and Python fallback use slightly different fallback tie-breaking and goal-node handling.

## Metrics

| Case | Policy | Faults | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Strict parity | Safety |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| first8 | edge_score_runtime | none | 8 | 8 | 78 | 78 | 0.000000000000 | 0 | 0 | True | True |
| first8 | shortest_safe_fallback | none | 7 | 8 | 184 | 73 | 0.167857142857 | 0 | 0 | False | True |
| first16 | edge_score_runtime | none | 16 | 16 | 173 | 173 | 0.000000000000 | 0 | 0 | True | True |
| first16 | shortest_safe_fallback | none | 12 | 16 | 613 | 198 | 3.716666666667 | 0 | 0 | False | True |
| fault_alt_route_first8 | edge_score_runtime | 16->17 | 8 | 8 | 74 | 74 | 0.000000000000 | 0 | 0 | True | True |
| fault_alt_route_first8 | shortest_safe_fallback | 16->17 | 7 | 8 | 184 | 73 | 0.167857142857 | 0 | 0 | False | True |
| fault_goal_exit_first8 | edge_score_runtime | 28->47 | 8 | 8 | 186 | 186 | 0.000000000000 | 0 | 0 | True | True |
| fault_goal_exit_first8 | shortest_safe_fallback | 28->47 | 7 | 8 | 244 | 155 | 11.003571428572 | 0 | 0 | False | True |

CSV: `outputs/tables/phase8_native_cpp_python_parity.csv`

## Gate Status

- EdgeScore native C++ vs Python strict replay parity: PASS
- fallback safety diagnostic: PASS
- fallback strict parity rows: `0/4`
- full high-throughput C++ event simulator parity: not covered

## Remaining Work

- align fallback tie-breaking and goal-node reservation semantics if fallback metric parity becomes a paper claim
- expand parity to larger windows, repair events, randomized density, and heldout maps
- replace the compact replay with the full C++ event scheduler before final runtime claims
