# Phase5 Fault Curriculum Smoke Report

Date: 2026-06-17

## Scope

This smoke adds fault-aware teacher slices before Phase6 RL fine-tuning. A fault-aware A* teacher generates recovery labels for selected fault windows, then the pure-Python MLP-EdgeScore behavior cloning model is retrained with base, DAgger, and fault-curriculum slices.

This is still a same-map smoke. It is not a heldout-map or RL result.

## Dataset

- Fault manifest: `artifacts/teacher/junction_slices_fault_curriculum_smoke.jsonl`
- Fault slices: `208`

## Metrics

| Case | Policy | Fault edges | Max tasks | Planned | Unplanned | Conflicts | Steps | Mean travel | Runtime seconds |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| density_train_first8 | base_dagger_bc | none | 8 | 8 | 0 | 0 | 78 | 49.750000 | 0.014965 |
| density_train_first8 | fault_curriculum_bc | none | 8 | 8 | 0 | 0 | 78 | 49.750000 | 0.015038 |
| density_train_first8 | fault_aware_astar | none | 8 | 8 | 0 | 0 | 78 | 49.750000 | 0.023262 |
| density_train_first8 | rolling_horizon_sipp | none | 8 | 8 | 0 | 0 | 8 | 50.456509 | 0.004226 |
| density_combined_first16 | base_dagger_bc | none | 16 | 15 | 1 | 0 | 192 | 51.586667 | 0.039281 |
| density_combined_first16 | fault_curriculum_bc | none | 16 | 16 | 0 | 0 | 173 | 57.012500 | 0.032453 |
| density_combined_first16 | fault_aware_astar | none | 16 | 15 | 1 | 0 | 192 | 51.586667 | 0.062194 |
| density_combined_first16 | rolling_horizon_sipp | none | 16 | 16 | 0 | 0 | 16 | 52.740501 | 0.009987 |
| fault_alt_route_first8 | base_dagger_bc | 16->17 | 8 | 4 | 4 | 0 | 544 | 47.000000 | 0.113052 |
| fault_alt_route_first8 | fault_curriculum_bc | 16->17 | 8 | 8 | 0 | 0 | 74 | 51.850000 | 0.011962 |
| fault_alt_route_first8 | fault_aware_astar | 16->17 | 8 | 8 | 0 | 0 | 74 | 51.850000 | 0.018364 |
| fault_alt_route_first8 | rolling_horizon_sipp | 16->17 | 8 | 8 | 0 | 0 | 8 | 53.606509 | 0.002368 |
| fault_goal_exit_first8 | base_dagger_bc | 28->47 | 8 | 0 | 8 | 0 | 1024 | 0.000000 | 0.191700 |
| fault_goal_exit_first8 | fault_curriculum_bc | 28->47 | 8 | 8 | 0 | 0 | 186 | 146.750000 | 0.035552 |
| fault_goal_exit_first8 | fault_aware_astar | 28->47 | 8 | 8 | 0 | 0 | 134 | 84.550000 | 0.046397 |
| fault_goal_exit_first8 | rolling_horizon_sipp | 28->47 | 8 | 8 | 0 | 0 | 8 | 84.242655 | 0.005261 |

CSV: `outputs/tables/phase5_fault_curriculum_metrics.csv`

## Gate Status

- zero post-shield conflicts: PASS
- fault curriculum improves selected fault recovery: PASS
- fault curriculum recovers selected fault smoke cases: PASS
- RL fine-tuning: not started

## Notes

The fault-curriculum BC policy improves recovery on the selected faults while remaining shield-safe. Travel times on fault cases are still worse than rolling-horizon SIPP, so SIPP remains the stronger recovery baseline.

## Remaining Work

- include fault-aware DAgger relabeling from model-visited failure states
- add repair-time and multi-fault curricula
- run larger windows and heldout-map validation
- only then start Phase6 RL fine-tuning from the fault-aware BC checkpoint
