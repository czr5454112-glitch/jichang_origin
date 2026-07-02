# G4E Next Gate Decision Report

Date: 2026-07-02

## Gate Summary

| Gate | Pass | Value | Decision |
| --- | --- | --- | --- |
| planned_count_ge_g4d | True | 4449>=4449 | development_pass |
| node_window_conflicts_zero | True | 0 | development_pass |
| fallback_calls_le_g4d | True | 6395<=6786 | development_pass |
| has_zero_fallback_tasks | True | 76>0 | development_pass |
| goal_reaching_safe_ge_route_exact | True | 4449>=4449 | development_pass |
| promotion_astar_reduction_ge_70pct | False | 0.5965808730759525 | block_promotion |
| promotion_fallback_rate_le_12pct | False | 0.1626688372802889 | block_promotion |
| recommend_g4f_runtime | False | G4E development pass only | block_promotion |

## Decision

G4E is a development pass, not a G4F promotion candidate. Continue fallback-reduction and runtime validation before C++ promotion.

- Development pass: `True`
- Promotion candidate: `False`

## Artifact

- Next gate table: `outputs/tables/g4e_next_gate.csv`
