# Phase8 Native C++ Repair-Window Parity Report

Date: 2026-06-17

## Scope

This diagnostic checks compact native C++ replay parity against the Python junction environment on `24`-task map2 windows with time-bounded fault/repair windows. A window is active when `fault_start <= ready_time < repair_time`; after `repair_time`, the edge is available again.

These rows validate repair-window semantics at the compact replay boundary. They are not a substitute for full Java route-update parity or the final high-throughput C++ event scheduler.

## Metrics

| Case | Offset | Repair windows | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Strict parity |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| repair_alt_route_first24 | 0 | 16->17@[0.000,10400.000) | 20 | 20 | 306 | 306 | 0.000000000000 | 0 | 0 | True |
| repair_goal_exit_first24 | 0 | 28->47@[0.000,10350.000) | 19 | 19 | 441 | 441 | 0.000000000000 | 0 | 0 | True |
| repair_branch_offset16 | 16 | 6->8@[10650.000,10750.000) | 16 | 16 | 509 | 509 | 0.000000000000 | 0 | 0 | True |
| repair_multi_window_offset32 | 32 | 16->17@[10700.000,10825.000);28->47@[10800.000,10950.000) | 18 | 18 | 419 | 419 | 0.000000000000 | 0 | 0 | True |

CSV: `outputs/tables/phase8_native_cpp_repair_parity.csv`

## Gate Status

- repair-window strict compact replay parity: PASS
- repair-window safety: PASS
- full fault/repair event scheduler parity: not covered
- heldout-map parity: not covered

## Remaining Work

- validate repair schedules on heldout and randomized maps
- move from compact decision replay to the final event scheduler before runtime-throughput claims
- expand repeated fault/repair schedule coverage after scheduler events are in place
