# Phase8 Native C++ Randomized Synthetic Parity Report

Date: 2026-06-17

## Scope

This diagnostic checks compact native C++ replay parity against the Python junction environment on fixed-seed synthetic directed ICS-like maps. The rows vary map edge lengths, optional branch edges, task density, static fault edges, and repair-window schedules.

The graph and task stream are passed through the pybind in-memory record API, so this is no longer limited to legacy `map2.txt` files. This is randomized synthetic-map coverage, not a real heldout airport map or the final high-throughput C++ event scheduler.

## Metrics

| Case | Seed | Tasks | Edges | Spacing | Static faults | Repair windows | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Strict parity |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| synthetic_seed7_medium_repair | 7 | 18 | 20 | 3.000 | none | 4->8@[4.000,18.000) | 18 | 18 | 55 | 55 | 0.000000000000 | True |
| synthetic_seed11_dense_multi_repair | 11 | 24 | 18 | 1.400 | none | 7->9@[5.000,16.000);8->9@[10.000,22.000) | 18 | 18 | 140 | 140 | 0.000000000000 | True |
| synthetic_seed17_static_plus_repair | 17 | 20 | 17 | 2.200 | 4->7 | 5->8@[0.000,14.000) | 14 | 14 | 247 | 247 | 0.000000000000 | True |
| synthetic_seed23_repeated_repair | 23 | 22 | 17 | 1.800 | none | 4->8@[3.000,8.000);4->8@[14.000,21.000);8->9@[9.000,15.000) | 20 | 20 | 128 | 128 | 0.000000000000 | True |

CSV: `outputs/tables/phase8_native_cpp_randomized_parity.csv`

## Gate Status

- randomized synthetic compact replay parity: PASS
- randomized synthetic safety: PASS
- real heldout-map parity: not covered
- full high-throughput event-scheduler parity: not covered

## Remaining Work

- add real heldout-map fixtures or map generators with persisted manifests
- carry the same randomized schedules into the final C++ event scheduler
- expand randomized density/fault seeds before paper-grade claims
