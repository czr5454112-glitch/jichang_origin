# Phase2 C++ PIBT-Style One-Step Parity Report

Date: 2026-06-17

## Scope

This diagnostic compares the Python PIBTStyleOneStepResolver against the C++ one-step resolver exposed through pybind. It covers deterministic priority ordering, same-slice merge conflicts, fault-edge fallback, existing node reservations, custom hold duration, and one persisted synthetic manifest slice.

This is one-step PIBT-style shield parity, not recursive PIBT/backtracking replay.

## Metrics

| Case | Agents | Fault edges | Node reservations | Holds Py/C++ | Python actions | C++ actions | Parity | First mismatch |
|---|---:|---:|---:|---:|---|---|---|---|
| merge_priority_conflict | 2 | 0 | 0 | 1/1 | 2:move:1->2;1:hold:0->0 | 2:move:1->2;1:hold:0->0 | True | match:none@ |
| merge_waiting_priority | 2 | 0 | 0 | 1/1 | 1:move:0->2;2:hold:1->1 | 1:move:0->2;2:hold:1->1 | True | match:none@ |
| merge_custom_hold_seconds | 2 | 0 | 0 | 1/1 | 2:move:1->2;1:hold:0->0 | 2:move:1->2;1:hold:0->0 | True | match:none@ |
| branch_fault_alternative | 1 | 1 | 0 | 0/0 | 3:move:0->2 | 3:move:0->2 | True | match:none@ |
| branch_reservation_alternative | 1 | 0 | 1 | 0/0 | 4:move:0->2 | 4:move:0->2 | True | match:none@ |
| synthetic_seed7_medium_repair_first_four_slice | 4 | 0 | 0 | 0/0 | 0:move:0->3;1:move:2->5;2:move:2->6;3:move:1->4 | 0:move:0->3;1:move:2->5;2:move:2->6;3:move:1->4 | True | match:none@ |

CSV: `outputs/tables/phase2_cpp_pibt_parity.csv`

## Gate Status

- C++ PIBT-style one-step Python/C++ parity: PASS
- merge/fault/reservation one-step shield cases: covered
- persisted synthetic manifest one-step slice: covered
- recursive priority inheritance/backtracking: not covered
- full active-bag replay integration: not covered
