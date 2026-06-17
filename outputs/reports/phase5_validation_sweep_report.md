# Phase5 Validation Sweep Report

Date: 2026-06-17

## Scope

This sweep validates the DAgger BC+shield smoke policy beyond the exact first-eight training replay. It trains a pure-Python MLP-EdgeScore model from the base teacher manifest plus the DAgger smoke manifest, then compares A*-guided baseline and DAgger BC closed-loop execution on training, heldout task-leg, and combined task windows.

This is a task-window heldout smoke on the same `map2` graph. It is not a heldout-map claim.

## Metrics

| Case | Policy | Max tasks | Planned | Unplanned | Conflicts | Steps | Mean travel | Runtime seconds |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| train_first8 | astar_guided | 8 | 8 | 0 | 0 | 78 | 49.750000 | 0.024172 |
| train_first8 | dagger_bc | 8 | 8 | 0 | 0 | 78 | 49.750000 | 0.013022 |
| heldout_next8 | astar_guided | 8 | 7 | 1 | 0 | 101 | 51.971429 | 0.033920 |
| heldout_next8 | dagger_bc | 8 | 7 | 1 | 0 | 101 | 51.971429 | 0.019847 |
| combined_first16 | astar_guided | 16 | 15 | 1 | 0 | 192 | 51.586667 | 0.059280 |
| combined_first16 | dagger_bc | 16 | 15 | 1 | 0 | 192 | 51.586667 | 0.034010 |

CSV: `outputs/tables/phase5_validation_sweep_metrics.csv`

## Gate Status

- zero post-shield conflicts: PASS
- heldout next8 planned count matches A*-guided smoke: PASS
- combined first16 planned count matches A*-guided smoke: PASS
- heldout map validation: not started

## Remaining Work

- add heldout-map or synthetic-map validation
- add fault and density sweeps
- compare against rolling-horizon SIPP and PIBT-style baselines on larger windows
- use this validation harness before Phase6 RL fine-tuning claims
