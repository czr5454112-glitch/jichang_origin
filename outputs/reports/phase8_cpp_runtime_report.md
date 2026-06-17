# Phase8 C++ Runtime Policy Smoke Report

Date: 2026-06-17

## Scope

This smoke uses the exported MLP-EdgeScore runtime text artifact from Phase8, loads it through both Python and C++, measures C++ pybind inference latency, and runs the C++ loaded scorer as the policy inside the existing shielded Python junction environment.

This is a runtime integration smoke. It is not yet a native C++ event-simulator replay.

## Runtime Artifact

- Model text artifact: `artifacts/runtime/phase8_edge_score_runtime_model.txt`
- Feature dimension: `13`
- Hidden dimension: `16`

## Inference Latency

| Mode | Samples | Repeats | Elapsed seconds | Decisions/s | Mismatches |
|---|---:|---:|---:|---:|---:|
| python_runtime_text | 208 | 200 | 3.176065 | 13097.97 | 0 |
| cpp_pybind_per_slice | 208 | 200 | 2.835985 | 14668.62 | 0 |
| cpp_predict_many | 208 | 200 | 2.297569 | 18106.09 | 0 |

Latency CSV: `outputs/tables/phase8_cpp_runtime_latency.csv`

## Closed-Loop Smoke

| Case | Policy | Fault edges | Tasks | Planned | Unplanned | Conflicts | Steps | Decisions/s | Truncated |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| density_train_first8 | python_runtime_text_policy | none | 8 | 8 | 0 | 0 | 78 | 6282.82 | False |
| density_train_first8 | cpp_runtime_policy | none | 8 | 8 | 0 | 0 | 78 | 5797.36 | False |
| density_combined_first16 | python_runtime_text_policy | none | 16 | 16 | 0 | 0 | 173 | 5599.72 | False |
| density_combined_first16 | cpp_runtime_policy | none | 16 | 16 | 0 | 0 | 173 | 6550.25 | False |
| fault_alt_route_first8 | python_runtime_text_policy | 16->17 | 8 | 8 | 0 | 0 | 74 | 5539.88 | False |
| fault_alt_route_first8 | cpp_runtime_policy | 16->17 | 8 | 8 | 0 | 0 | 74 | 5847.12 | False |
| fault_goal_exit_first8 | python_runtime_text_policy | 28->47 | 8 | 8 | 0 | 0 | 186 | 5357.10 | False |
| fault_goal_exit_first8 | cpp_runtime_policy | 28->47 | 8 | 8 | 0 | 0 | 186 | 5116.82 | False |

Closed-loop CSV: `outputs/tables/phase8_cpp_runtime_closed_loop.csv`

## Gate Status

- C++ text artifact load: PASS
- C++ batch inference parity: PASS
- runtime latency measured: PASS
- C++ runtime policy closed-loop smoke: PASS
- C++ runtime policy matches Python artifact planned counts: PASS
- native C++ event replay: not covered
- model-unavailable fallback: covered by unit test, not this script

## Remaining Work

- move the event replay loop itself into C++ instead of only calling C++ inference from Python
- add larger batch latency sweeps and compare against rolling-horizon/SIPP runtime under identical task windows
- validate runtime checkpoints on heldout maps, randomized density windows, and repair schedules
