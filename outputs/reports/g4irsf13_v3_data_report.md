# G4IRSF13 v3 Residual Data Report

Status: `PASS` for observational F2-preservation
pretraining. Corrective-learning promotion remains blocked.

## Bound real evidence

- Map: `map2.json`, raw SHA-256 `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4`.
- Tasks: `inputdata.jsonl`, `43,603` segments and
  `28,506` raw bags, SHA-256 `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f`.
- Actual local decisions: `3,501`.
- Actual candidate records: `6,259`.
- Exact outgoing-candidate completeness:
  `1.000`.
- Actual selected-action coverage:
  `1.000`.
- Main raw-bag split overlap: `0`.
- Independent source/goal/time/junction/storage/motif held-out views:
  `6` PASS, each with raw-bag
  overlap `0`; the single observed fault regime is explicitly not applicable.

The decision file contains only decision-time local state. Label provenance,
confidence, weak-teacher status, future-dependency status, and post-hoc
outcomes live in separate hash-bound files and are not model features.
The main train/validation/audit split is grouped by raw bag. Dimension
generalization uses separate grouped views: if any decision matches that
view's held-out value, the entire raw bag is removed from the view's training
side.

## Hard cohort

- `detour`: 761
- `f2_slower_than_v2`: 232
- `first_divergence`: 1841
- `high_wait`: 450
- `merge_contention`: 454
- `p2_involvement`: 6
- `storage_out`: 452

## Easy cohort

- `unique_outgoing_edge`: 743
- `high_margin_f2_choice`: 891
- `no_contention`: 636
- `direct_goal`: 395
- `f2_v2_current_action_agreement`: 1660

## Label authority

Level-A rank targets are computed from the same decision's local
travel/calendar/service, short queue bound, cycle/trap, credit, and
merge-local burden. The formula is versioned as `g4irsf13_level_a_one_step_projection_v1` and
has `1,363` corrective decisions
with `2` abstentions. It is only a
one-step projection, not a full-outcome or causal TTH label.

Stage B recorded v2's locally feasible current action, but its full
counterfactual status is `NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE`.
Disagreeing v2 actions remain weak-teacher metadata and risk evidence only.

## Promotion blockers

- closed-loop 144/512/2048/8192/full ladder has not run
- independent residual learning contribution is not demonstrated
- strict F2 and v2-safe win is not demonstrated
