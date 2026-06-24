# Phase8 C++ Runtime Policy Smoke Report

Date: 2026-06-24

## Scope

This smoke uses the exported MLP-EdgeScore runtime text artifact from Phase8, loads it through both Python and C++, measures C++ pybind inference latency, and runs the C++ loaded scorer as the policy inside the existing shielded Python junction environment.

This script is the local C++ inference and Python-environment closed-loop smoke. Native C++ compact replay, event replay, repair-window replay, and model-unavailable fallback evidence are tracked by the later Phase8 reports linked in the gate status below.

## Runtime Artifact

- Model text artifact: `artifacts/runtime/phase8_edge_score_runtime_model.txt`
- Feature dimension: `13`
- Hidden dimension: `16`

## Inference Latency

| Mode | Samples | Repeats | Elapsed seconds | Decisions/s | Mismatches |
|---|---:|---:|---:|---:|---:|
| python_runtime_text | 208 | 200 | 3.214235 | 12942.43 | 0 |
| cpp_pybind_per_slice | 208 | 200 | 2.971629 | 13999.06 | 0 |
| cpp_predict_many | 208 | 200 | 2.539669 | 16380.09 | 0 |

Latency CSV: `outputs/tables/phase8_cpp_runtime_latency.csv`

## Closed-Loop Smoke

| Case | Policy | Fault edges | Tasks | Planned | Unplanned | Conflicts | Steps | Decisions/s | Truncated |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| density_train_first8 | python_runtime_text_policy | none | 8 | 8 | 0 | 0 | 78 | 1516.65 | False |
| density_train_first8 | cpp_runtime_policy | none | 8 | 8 | 0 | 0 | 78 | 1309.05 | False |
| density_combined_first16 | python_runtime_text_policy | none | 16 | 16 | 0 | 0 | 173 | 1287.49 | False |
| density_combined_first16 | cpp_runtime_policy | none | 16 | 16 | 0 | 0 | 173 | 1304.38 | False |
| fault_alt_route_first8 | python_runtime_text_policy | 16->17 | 8 | 8 | 0 | 0 | 74 | 1258.45 | False |
| fault_alt_route_first8 | cpp_runtime_policy | 16->17 | 8 | 8 | 0 | 0 | 74 | 1271.78 | False |
| fault_goal_exit_first8 | python_runtime_text_policy | 28->47 | 8 | 8 | 0 | 0 | 186 | 1373.05 | False |
| fault_goal_exit_first8 | cpp_runtime_policy | 28->47 | 8 | 8 | 0 | 0 | 186 | 1303.63 | False |

Closed-loop CSV: `outputs/tables/phase8_cpp_runtime_closed_loop.csv`

## Gate Status

- C++ text artifact load: PASS
- C++ batch inference parity: PASS
- runtime latency measured: PASS
- C++ runtime policy closed-loop smoke: PASS
- C++ runtime policy matches Python artifact planned counts: PASS
- native C++ event replay: covered by `outputs/reports/phase8_native_cpp_event_parity_report.md` and `outputs/reports/phase8_legacy_event_parity_report.md`
- model-unavailable fallback: covered by native fallback replay reports and pybind smoke
- safety constraints independent of neural output: PASS; hard action masks, C++ shield checks, and fallback replay remain available without model output

## Remaining Work

- add larger batch latency sweeps and compare against rolling-horizon/SIPP runtime under identical task windows
- validate runtime checkpoints on heldout maps, randomized density windows, and repair schedules
