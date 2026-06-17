# Phase8 Native C++ Offset/Fault Parity Report

Date: 2026-06-17

## Scope

This diagnostic checks compact native C++ replay parity against the Python junction environment on `24`-task windows selected from deterministic offsets plus fixed-seed randomized offsets. Each row applies either no fault or one static fault edge. This is not repair-event or heldout-map validation.

Random seed: `20260617`

## Metrics

| Case | Offset | Faults | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Strict parity |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| offset_0_none | 0 | none | 20 | 20 | 302 | 302 | 0.000000000000 | 0 | 0 | True |
| offset_8_alt_route_16_17 | 8 | 16->17 | 17 | 17 | 428 | 428 | 0.000000000000 | 0 | 0 | True |
| offset_16_goal_exit_28_47 | 16 | 28->47 | 10 | 10 | 1285 | 1285 | 0.000000000000 | 0 | 0 | True |
| offset_32_branch_6_8 | 32 | 6->8 | 18 | 18 | 410 | 410 | 0.000000000000 | 0 | 0 | True |
| offset_10_none | 10 | none | 16 | 16 | 352 | 352 | 0.000000000000 | 0 | 0 | True |
| offset_35_alt_route_16_17 | 35 | 16->17 | 20 | 20 | 408 | 408 | 0.000000000000 | 0 | 0 | True |
| offset_87_goal_exit_28_47 | 87 | 28->47 | 13 | 13 | 850 | 850 | 0.000000000000 | 0 | 0 | True |
| offset_99_branch_6_8 | 99 | 6->8 | 24 | 24 | 392 | 392 | 0.000000000000 | 0 | 0 | True |

CSV: `outputs/tables/phase8_native_cpp_offset_fault_parity.csv`

## Gate Status

- offset/fault strict compact replay parity: PASS
- offset/fault safety: PASS
- full repair-event parity: not covered
- heldout-map parity: not covered

## Remaining Work

- add repair-event schedules rather than static fault edges
- validate heldout maps and randomized synthetic maps
- replace compact replay with the full C++ event scheduler before final runtime claims
