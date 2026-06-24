# Phase2 PIBT Active-Bag Replay Parity Report

Date: 2026-06-24

## Scope

This diagnostic compares the Python and C++ active-bag PIBT-style replay baseline. Each tick admits arrived bags, resolves all ready active bags with the bounded recursive PIBT one-step resolver, commits moves/holds, and continues until each bag is planned or the tick limit is reached.

It covers two active bags, static-fault alternate routing, repair-window behavior, recursive handoff inside an active-bag slice, merge-group capacity, and two persisted synthetic manifest slices.

## Metrics

| Case | Tasks | Interval | Py/C++ planned | Py/C++ decisions | Py/C++ ticks | Peak active Py/C++ | Holds Py/C++ | Events Py/C++ | Parity | First mismatch |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| line_two_active_bags | 2 | 2.0 | 2/2 | 4/4 | 3/3 | 2/2 | 0/0 | 8/8 | True | match:none@ |
| branch_static_fault_alternative | 1 | 2.0 | 1/1 | 2/2 | 2/2 | 1/1 | 0/0 | 4/4 | True | match:none@ |
| branch_repaired_preferred_edge | 1 | 2.0 | 1/1 | 2/2 | 2/2 | 1/1 | 0/0 | 4/4 | True | match:none@ |
| handoff_active_bag_slice | 2 | 2.0 | 2/2 | 3/3 | 2/2 | 2/2 | 0/0 | 7/7 | True | match:none@ |
| parallel_merge_group_capacity | 2 | 2.0 | 2/2 | 5/5 | 3/3 | 2/2 | 1/1 | 9/9 | True | match:none@ |
| synthetic_seed7_medium_repair_pibt_active | 6 | 5.0 | 6/6 | 18/18 | 7/7 | 4/4 | 0/0 | 30/30 | True | match:none@ |
| synthetic_seed11_dense_multi_repair_pibt_active | 6 | 5.0 | 6/6 | 25/25 | 9/9 | 6/6 | 5/5 | 37/37 | True | match:none@ |

CSV: `outputs/tables/phase2_pibt_active_bag_replay_parity.csv`

## Gate Status

- PIBT active-bag replay Python/C++ parity: PASS
- post-shield safety: PASS
- recursive handoff inside active-bag replay: covered
- merge-group active-bag replay: covered
- persisted synthetic manifest slices: covered
