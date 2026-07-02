# G4E True Decentralized Closed-Loop Report

Date: 2026-07-02

## Scope

This evaluates route-exact accounting plus two learner-visited goal-reaching modes. Model-only and fallback-assisted modes allow the learner to deviate from the CIE path, then measure whether it still reaches the goal with zero node-window conflicts.

## Closed-Loop Comparison

| Mode | Planned | Route exact | Deviated success | Fallback calls | Zero-fallback tasks | Failures |
| --- | --- | --- | --- | --- | --- | --- |
| route_exact_with_g4e_fallback | 4449/4449 | 4449 | 0 | 6395 | 76 | 0 |
| goal_reaching_model_only | 4449/4449 | 2850 | 1599 | 0 | 4449 | 0 |
| goal_reaching_with_g4e_fallback | 4449/4449 | 3077 | 1372 | 6644 | 76 | 0 |

## Teacher Boundary

- Teacher no-path boundary rows: `47`

## Decision

G4E records true learner-visited goal-reaching behavior separately from route-exact imitation. Model-only deviations are diagnostic; the engineering policy remains fallback-assisted until the local-wait decentralized loop is validated in the runtime/export path.

## Artifacts

- Model-only summary: `outputs/tables/g4e_model_only_route_success.csv`
- Deviation outcomes: `outputs/tables/g4e_learner_deviation_outcomes.csv`
- Closed-loop comparison: `outputs/tables/g4e_closed_loop_comparison.csv`
- Teacher boundary: `outputs/tables/g4e_teacher_no_path_boundary.csv`
