# Phase2 C++ PIBT-Style Recursive Parity Report

Date: 2026-06-17

## Scope

This diagnostic compares the Python PIBTStyleOneStepResolver against the C++ resolver exposed through pybind. It covers deterministic priority ordering, same-slice merge conflicts, fault-edge fallback, existing node reservations, custom hold duration, bounded recursive current-node handoff, and one persisted synthetic manifest slice.

This is slice-level PIBT-style shield parity, not full active-bag PIBT replay integration.

## Metrics

| Case | Agents | Fault edges | Node reservations | Holds Py/C++ | Python actions | C++ actions | Parity | First mismatch |
|---|---:|---:|---:|---:|---|---|---|---|
| merge_priority_conflict | 2 | 0 | 0 | 1/1 | 2:move:1->2:best_safe_edge;1:hold:0->0:no_safe_edge | 2:move:1->2:best_safe_edge;1:hold:0->0:no_safe_edge | True | match:none@ |
| merge_waiting_priority | 2 | 0 | 0 | 1/1 | 1:move:0->2:best_safe_edge;2:hold:1->1:no_safe_edge | 1:move:0->2:best_safe_edge;2:hold:1->1:no_safe_edge | True | match:none@ |
| merge_custom_hold_seconds | 2 | 0 | 0 | 1/1 | 2:move:1->2:best_safe_edge;1:hold:0->0:no_safe_edge | 2:move:1->2:best_safe_edge;1:hold:0->0:no_safe_edge | True | match:none@ |
| branch_fault_alternative | 1 | 1 | 0 | 0/0 | 3:move:0->2:best_safe_edge | 3:move:0->2:best_safe_edge | True | match:none@ |
| branch_reservation_alternative | 1 | 0 | 1 | 0/0 | 4:move:0->2:best_safe_edge | 4:move:0->2:best_safe_edge | True | match:none@ |
| handoff_priority_inheritance | 2 | 0 | 0 | 0/0 | 1:move:0->1:priority_inheritance;2:move:1->3:inherited_move | 1:move:0->1:priority_inheritance;2:move:1->3:inherited_move | True | match:none@ |
| handoff_blocked_uses_alternative | 2 | 0 | 0 | 0/0 | 1:move:0->2:best_safe_edge;2:move:1->0:best_safe_edge | 1:move:0->2:best_safe_edge;2:move:1->0:best_safe_edge | True | match:none@ |
| synthetic_seed7_medium_repair_first_four_slice | 4 | 0 | 0 | 0/0 | 0:move:0->3:best_safe_edge;1:move:2->5:best_safe_edge;2:move:2->6:best_safe_edge;3:move:1->4:best_safe_edge | 0:move:0->3:best_safe_edge;1:move:2->5:best_safe_edge;2:move:2->6:best_safe_edge;3:move:1->4:best_safe_edge | True | match:none@ |

CSV: `outputs/tables/phase2_cpp_pibt_parity.csv`

## Gate Status

- C++ PIBT-style Python/C++ parity: PASS
- merge/fault/reservation one-step shield cases: covered
- bounded recursive current-node handoff: covered
- persisted synthetic manifest one-step slice: covered
- full active-bag replay integration: not covered
