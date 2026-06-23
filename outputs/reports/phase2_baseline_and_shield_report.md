# Phase2 Baseline and Shield Smoke Report

Date: 2026-06-17

## Scope

This smoke runs two non-learning baselines on the same first `128` expanded task legs
from `inputdata.jsonl`:

- `reference_astar`: Phase1 Python A* reference replay
- `rolling_horizon_sipp`: Phase2 rolling-window SIPP baseline with horizon `300.0` seconds

This is still a smoke replay, not a full benchmark. It exercises node and edge reservation safety
plus baseline logging on real task-stream inputs.

## Metrics

| Baseline | Planned | Unplanned | Post-shield conflicts | Mean travel | P95 travel | Runtime seconds |
|---|---:|---:|---:|---:|---:|---:|
| reference_astar | 113 | 15 | 0 | 51.529204 | 76.800000 | 0.045239 |
| rolling_horizon_sipp | 128 | 0 | 0 | 87.705494 | 161.469291 | 0.118812 |

CSV: `outputs/tables/phase2_baseline_smoke_metrics.csv`

Active-bag/replan-cost evidence is tracked separately in
`outputs/reports/phase2_active_bag_replanning_audit_report.md`.

Route-discarding periodic active-bag replanning parity is tracked in
`outputs/reports/phase2_periodic_replanning_parity_report.md`.

PIBT-style recursive current-node handoff parity is tracked in
`outputs/reports/phase2_cpp_pibt_parity_report.md`.

Active-bag PIBT replay parity is tracked in
`outputs/reports/phase2_pibt_active_bag_replay_parity_report.md`.

## Gate Status

- post-shield/reservation conflicts: PASS
- reproducible baseline entry point: PASS
- full Phase2 baseline stack: incomplete

## Remaining Work

- full merge-group replay integration across every baseline
- full buffer-capacity replay integration across every baseline
- rolling-horizon active-bag replanning rather than sequential task-leg replay
- real heldout airport-map fixtures
- larger multi-seed task-density/fault sweeps
