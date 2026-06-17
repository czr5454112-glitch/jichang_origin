# Phase2 Baseline and Shield Smoke Report

Date: 2026-06-17

## Scope

This smoke runs two non-learning baselines on the same first `128` expanded task legs from `inputdata.jsonl`:

- `reference_astar`: Phase1 Python A* reference replay
- `rolling_horizon_sipp`: Phase2 rolling-window SIPP baseline with horizon `300.0` seconds

This is still a smoke replay, not a full benchmark. It exercises node reservation safety and baseline logging on real task-stream inputs.

## Metrics

| Baseline | Planned | Unplanned | Reservation conflicts | Mean travel | P95 travel | Runtime seconds |
|---|---:|---:|---:|---:|---:|---:|
| reference_astar | 113 | 15 | 0 | 51.529204 | 76.800000 | 0.067894 |
| rolling_horizon_sipp | 128 | 0 | 0 | 48.320226 | 52.600000 | 0.109053 |

CSV: `outputs/tables/phase2_baseline_smoke_metrics.csv`

## Gate Status

- post-shield/reservation conflicts: PASS
- reproducible baseline entry point: PASS
- full Phase2 baseline stack: incomplete

## Remaining Work

- SIPP with edge capacity/headway and merge constraints
- rolling-horizon active-bag replanning rather than sequential task-leg replay
- PIBT/CS-PIBT-style resolver integration and recursive priority inheritance
- larger multi-seed task-density/fault sweeps
