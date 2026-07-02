# G3e Event-Semantics Repair

Date: 2026-07-02

## Scope

This pass fixes and validates one concrete event-horizon semantic bug: downstream repair-window faults should not make upstream waiting nodes look permanently unreachable. It is not training, not G4A scaling, and not a relaxation of hard edge-capacity safety.

## Repair-Window Reachability Cases

| Case | Safe | Reasons | Pass |
| --- | --- | --- | --- |
| repairable_downstream_fault | True | none | True |
| permanent_downstream_fault | False | unreachable_goal | True |
| currently_faulted_candidate_edge | False | fault_edge | True |

Reachability semantic tests: `PASS`.

## Matched-Window Gate After Repair

| Variant | Planned | Branch Coverage | Conflicts | Real Conflicts | Gate |
| --- | --- | --- | --- | --- | --- |
| ablation_disable_edge_capacity | 125/144 | 1.000 | 0 | 491 | False |
| ablation_edge_capacity_2 | 96/144 | 0.780 | 0 | 131 | False |
| g3c_baseline_reproduction | 78/144 | 0.487 | 0 | 0 | False |
| hybrid_legacy_wait_sipp_fallback | 92/144 | 0.958 | 0 | 0 | False |
| jump_to_earliest_safe_time | 88/144 | 0.932 | 0 | 0 | False |
| reroute_from_current_legacy | 94/144 | 0.642 | 0 | 0 | False |
| wait_fixed_hold_5s | 93/144 | 0.969 | 0 | 0 | False |

## Decision

Continue event-capacity repair before G4A. The repair-window reachability fix is validated, but best primary replay is still 94/144, below the 115/144 gate. Edge-capacity ablation reaches 125/144 but has 491 real-constraint conflicts, so the remaining blocker is not safe to bypass.

## Artifacts

- Reachability cases: `outputs/tables/g3e_repair_window_reachability_cases.csv`
- Matched gate table: `outputs/tables/g3e_matched_gate_after_repair.csv`
