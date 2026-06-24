# Phase2 Baseline and Shield Smoke Report

Date: 2026-06-24

## Scope

This smoke runs three non-learning baselines on the same first `128` expanded task legs
from `inputdata.jsonl`:

- `reference_astar`: Phase1 Python A* reference replay
- `queue_aware_shortest_path`: Phase2 queue-aware SIPP route replay with local queue-pressure penalties
- `rolling_horizon_sipp`: Phase2 rolling-window SIPP baseline with horizon `300.0` seconds

This is still a smoke replay, not a full benchmark. It exercises node and edge reservation safety
plus baseline logging on real task-stream inputs. C++ coverage for SIPP, rolling-horizon, PIBT, and
QueueAwareShortestPath is verified by the CTest core smoke and the dedicated parity reports listed below.

## Metrics

| Baseline | Planned | Unplanned | Post-shield conflicts | Mean travel | P95 travel | Runtime seconds |
|---|---:|---:|---:|---:|---:|---:|
| reference_astar | 113 | 15 | 0 | 51.529204 | 76.800000 | 0.041494 |
| queue_aware_shortest_path | 128 | 0 | 0 | 84.657354 | 150.413295 | 0.174542 |
| rolling_horizon_sipp | 128 | 0 | 0 | 87.705494 | 161.469291 | 0.178441 |

CSV: `outputs/tables/phase2_baseline_smoke_metrics.csv`

Active-bag/replan-cost evidence is tracked separately in
`outputs/reports/phase2_active_bag_replanning_audit_report.md`.

Route-discarding periodic active-bag replanning parity is tracked in
`outputs/reports/phase2_periodic_replanning_parity_report.md`.

PIBT-style recursive current-node handoff parity is tracked in
`outputs/reports/phase2_cpp_pibt_parity_report.md`.

Active-bag PIBT replay parity is tracked in
`outputs/reports/phase2_pibt_active_bag_replay_parity_report.md`.

## Named Phase2 Stack Coverage

| Required item | Evidence |
|---|---|
| `ReservationTable` | Python/C++ node intervals, edge intervals, capacity, headway, buffer, and merge-group tests |
| `SIPPPlanner` | Python smoke rows plus `outputs/reports/phase2_cpp_sipp_parity_report.md` |
| `RollingHorizonPlanner` | implemented as `RollingHorizonBaseline` / C++ `run_rolling_horizon_sipp`; parity report linked above |
| `QueueAwareShortestPath` | Python replay row in this report plus C++ core smoke for future-queue avoidance |
| `PIBTStyleOneStepResolver` | `outputs/reports/phase2_cpp_pibt_parity_report.md` and active-bag replay parity |
| `JunctionShield` | hard node/edge/buffer/merge/fault checks used by action masks, PIBT, runtime fallback, and C++ shield tests |

## Gate Status

- post-shield/reservation conflicts: PASS
- reproducible baseline entry point: PASS
- named Phase2 baseline/shield stack smoke coverage: PASS

## Remaining Work

- paper-grade multi-seed task-density/fault sweeps across every baseline family
- separate real heldout airport-map fixtures when available
- broader non-synthetic topology validation before paper-grade stress claims
