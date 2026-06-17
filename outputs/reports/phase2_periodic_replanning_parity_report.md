# Phase2 Periodic Replanning Parity Report

Date: 2026-06-17

## Scope

This diagnostic compares the Python and C++ periodic active-bag SIPP replanning baseline. Each tick replans from the bag's current node, commits only the next hop, and discards the rest of the planned route before the next tick.

It covers two active bags, edge-capacity pressure, static-fault alternate routing, and two persisted synthetic manifest slices. Repair windows, recursive PIBT, and real heldout airport maps are not covered.

## Metrics

| Case | Tasks | Interval | Py/C++ planned | Py/C++ replans | Py/C++ ticks | Peak active Py/C++ | Events Py/C++ | Parity | First mismatch |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| line_two_active_bags | 2 | 2.0 | 2/2 | 4/4 | 3/3 | 2/2 | 8/8 | True | match:none@ |
| single_edge_capacity | 2 | 2.0 | 2/2 | 2/2 | 2/2 | 1/1 | 6/6 | True | match:none@ |
| branch_static_fault_alternative | 1 | 2.0 | 1/1 | 2/2 | 2/2 | 1/1 | 4/4 | True | match:none@ |
| synthetic_seed7_medium_repair_periodic | 8 | 5.0 | 8/8 | 24/24 | 9/9 | 5/5 | 40/40 | True | match:none@ |
| synthetic_seed11_dense_multi_repair_periodic | 8 | 5.0 | 8/8 | 26/26 | 8/8 | 8/8 | 42/42 | True | match:none@ |

CSV: `outputs/tables/phase2_periodic_replanning_parity.csv`

## Gate Status

- periodic replanning Python/C++ parity: PASS
- post-shield safety: PASS
- route-discarding one-step replanning: covered
- static-fault alternate routing: covered
- repair-window periodic replanning: not covered
- recursive PIBT: not covered
