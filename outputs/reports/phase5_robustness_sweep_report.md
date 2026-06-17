# Phase5 Robustness Sweep Report

Date: 2026-06-17

## Scope

This diagnostic compares A*-guided junction policy, DAgger BC+shield, and rolling-horizon SIPP on small density and fault windows before starting Phase6 RL fine-tuning. It is intentionally allowed to expose failures so the fault curriculum has concrete targets.

## Metrics

| Case | Policy | Fault edges | Max tasks | Planned | Unplanned | Conflicts | Steps | Mean travel | Runtime seconds |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| density_train_first8 | astar_guided | none | 8 | 8 | 0 | 0 | 78 | 49.750000 | 0.024638 |
| density_train_first8 | dagger_bc | none | 8 | 8 | 0 | 0 | 78 | 49.750000 | 0.013625 |
| density_train_first8 | rolling_horizon_sipp | none | 8 | 8 | 0 | 0 | 8 | 50.456509 | 0.005459 |
| density_heldout_next8 | astar_guided | none | 8 | 7 | 1 | 0 | 101 | 51.971429 | 0.029784 |
| density_heldout_next8 | dagger_bc | none | 8 | 7 | 1 | 0 | 101 | 51.971429 | 0.016962 |
| density_heldout_next8 | rolling_horizon_sipp | none | 8 | 8 | 0 | 0 | 8 | 57.765529 | 0.004197 |
| density_combined_first16 | astar_guided | none | 16 | 15 | 1 | 0 | 192 | 51.586667 | 0.064880 |
| density_combined_first16 | dagger_bc | none | 16 | 15 | 1 | 0 | 192 | 51.586667 | 0.041700 |
| density_combined_first16 | rolling_horizon_sipp | none | 16 | 16 | 0 | 0 | 16 | 52.740501 | 0.008298 |
| fault_alt_route_first8 | astar_guided | 16->17 | 8 | 8 | 0 | 0 | 74 | 51.850000 | 0.024471 |
| fault_alt_route_first8 | dagger_bc | 16->17 | 8 | 4 | 4 | 0 | 544 | 47.000000 | 0.097394 |
| fault_alt_route_first8 | rolling_horizon_sipp | 16->17 | 8 | 8 | 0 | 0 | 8 | 53.606509 | 0.002708 |
| fault_goal_exit_first8 | astar_guided | 28->47 | 8 | 0 | 8 | 0 | 1024 | 0.000000 | 0.284781 |
| fault_goal_exit_first8 | dagger_bc | 28->47 | 8 | 0 | 8 | 0 | 1024 | 0.000000 | 0.203590 |
| fault_goal_exit_first8 | rolling_horizon_sipp | 28->47 | 8 | 8 | 0 | 0 | 8 | 84.242655 | 0.005271 |

CSV: `outputs/tables/phase5_robustness_sweep_metrics.csv`

## Diagnostic Status

- zero post-shield conflicts: PASS
- fault cases expose BC robustness gap: YES
- rolling-horizon SIPP recovers at least one fault case: YES
- Phase6 fault curriculum target defined: PASS

## Notes

The DAgger BC policy remains shield-safe, but it does not yet learn robust fallback behavior under selected faults. Rolling-horizon SIPP remains a stronger recovery baseline in these diagnostics.

## Remaining Work

- add fault-aware teacher slices and DAgger relabeling
- train/evaluate BC on fault curriculum before RL
- compare against PIBT-style resolver on simultaneous junction slices
- expand density and repair-time sweeps
