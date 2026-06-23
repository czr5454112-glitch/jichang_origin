# Phase2 C++ Rolling-Horizon SIPP Parity Report

Date: 2026-06-23

## Scope

This diagnostic compares the Python rolling-horizon SIPP baseline against the C++ rolling-horizon SIPP replay through pybind. It checks aggregate summaries and planned/unplanned event rows across priority, static fault, repair-window fault, edge-capacity, edge-headway, node buffer-capacity, and persisted synthetic-map schedules.

## Metrics

| Case | Tasks | Horizon | Py planned | C++ planned | Py unplanned | C++ unplanned | Mean diff | Events | Parity | First mismatch |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| line_priority | 2 | 60.0 | 2 | 2 | 0 | 0 | 0.000000000000 | 2/2 | True | match:none@ |
| line_fault_unplanned | 1 | 300.0 | 0 | 0 | 1 | 1 | 0.000000000000 | 1/1 | True | match:none@ |
| line_repair_window_recovered | 1 | 300.0 | 1 | 1 | 0 | 0 | 0.000000000000 | 1/1 | True | match:none@ |
| line_repair_window_active_unplanned | 1 | 300.0 | 0 | 0 | 1 | 1 | 0.000000000000 | 1/1 | True | match:none@ |
| single_edge_capacity | 2 | 60.0 | 2 | 2 | 0 | 0 | 0.000000000000 | 2/2 | True | match:none@ |
| single_edge_headway | 2 | 60.0 | 2 | 2 | 0 | 0 | 0.000000000000 | 2/2 | True | match:none@ |
| line_buffer_capacity | 2 | 60.0 | 2 | 2 | 0 | 0 | 0.000000000000 | 2/2 | True | match:none@ |
| synthetic_seed7_medium_repair_rolling | 18 | 6.0 | 18 | 18 | 0 | 0 | 0.000000000000 | 18/18 | True | match:none@ |
| synthetic_seed11_dense_multi_repair_rolling | 24 | 6.0 | 24 | 24 | 0 | 0 | 0.000000000000 | 24/24 | True | match:none@ |
| synthetic_seed17_static_plus_repair_rolling | 20 | 6.0 | 20 | 20 | 0 | 0 | 0.000000000000 | 20/20 | True | match:none@ |
| synthetic_seed23_repeated_repair_rolling | 22 | 6.0 | 22 | 22 | 0 | 0 | 0.000000000000 | 22/22 | True | match:none@ |
| synthetic_seed31_merge_buffer_rolling | 26 | 6.0 | 26 | 26 | 0 | 0 | 0.000000000000 | 26/26 | True | match:none@ |

CSV: `outputs/tables/phase2_cpp_rolling_horizon_parity.csv`

## Gate Status

- C++ rolling-horizon Python/C++ parity: PASS
- rolling-horizon post-shield safety: PASS
- persisted synthetic manifest schedules: covered
- repair-window rolling-horizon planning-time semantics: covered
- node buffer-capacity rolling-horizon planning semantics: covered
- full active-bag PIBT replay and full merge-group replay integration: not covered
