# G4E Runtime Call Accounting Report

Date: 2026-07-02

## Scope

This report separates interface-level savings, task-level zero-fallback share, and original CIE retry A* attempt reduction. Timing is a call-count proxy, not a real runtime speedup claim.

## A* Accounting

| Policy | Planned | Fallback A* | A* Reduction | 0-fallback tasks | Interpretation |
| --- | --- | --- | --- | --- | --- |
| cie_retry_teacher_baseline | 4449/4449 | 15852 | 0.0 | 0/4449 | original task-level CIE retry baseline |
| g4d_route_exact_risk_head | 4449/4449 | 6786 | 0.5719152157456473 | 0/4449 | G4D aggregate A* reduction but zero task-level full replacement |
| g4e_route_exact_risk_reduced | 4449/4449 | 6395 | 0.5965808730759525 | 76/4449 | reduces A* calls and improves task-level zero-fallback share |
| g4e_goal_reaching_model_only | 4449/4449 | 0 | 1.0 | 4449/4449 | diagnostic: no A* after admission, but requires runtime validation before deployment |
| g4e_goal_reaching_with_fallback | 4449/4449 | 6644 | 0.5808730759525612 | 76/4449 | reduces A* calls and improves task-level zero-fallback share |

## Decision

G4E reduces route-exact fallback calls relative to G4D and introduces a nonzero zero-fallback task share. It does not reach the 70% A* reduction / 12% fallback-rate promotion target, so it remains a development pass rather than a G4F promotion candidate.

## Artifact

- A* accounting: `outputs/tables/g4e_astar_call_accounting.csv`
