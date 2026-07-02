# G3i CIE/A* Path-Constrained SIPP Integration

Date: 2026-07-02

## 1. Scope

G3i integrates SIPP into the execution layer without replacing the original CIE/Legacy A* teacher. CIE/A* still chooses the route; the SIPP-style wrapper only retimes that fixed route around node, edge, and merge reservations.

## 2. Real ICS simulation result

| Scenario | Planned | Conflicts | A* path matches | Waited tasks |
| --- | --- | --- | --- | --- |
| legacy_first16 | 16/16 | 0 | 16/16 | 8 |
| legacy_first16_buffer2 | 16/16 | 0 | 16/16 | 8 |
| legacy_first32 | 32/32 | 0 | 32/32 | 20 |
| legacy_offset32_static16 | 16/16 | 0 | 16/16 | 12 |
| legacy_offset64_repair32 | 26/32 | 0 | 26/26 | 22 |
| legacy_offset64_merge32 | 26/32 | 0 | 26/26 | 21 |

Aggregate: `132/144` planned, `0` real node/edge/merge conflicts, `132/132` planned routes keep the original A* path.

## 3. Gates

| Gate | Pass | Value | Decision |
| --- | --- | --- | --- |
| sipp_integrated_without_replacing_cie_teacher | True | cie_path_fixed_sipp_timing_only | keep_cie_as_teacher |
| same_astar_path_effect_for_planned_routes | True | 132/132 | path_effect_preserved |
| airport_ics_simulation_runs | True | 132/144 | integration_runs_on_map2_inputdata |
| hard_runtime_constraints_clean | True | 0 | safe_to_continue_g4a_pilot_audit |
| planned_count_gate | True | 132 | g4a_pilot_candidate_after_review |
| remaining_unplanned_inventory | True | 12 | audit_remaining_no_path_cases |

## 4. Remaining unplanned cases

| Scenario | Reason | Count |
| --- | --- | --- |
| legacy_offset64_merge32 | legacy_astar_no_path | 6 |
| legacy_offset64_repair32 | legacy_astar_no_path | 6 |

## 5. Decision

Integration pass: SIPP is now usable as an execution-timing wrapper around the existing CIE/A* route effect. This is a G4A pilot candidate, but the remaining no-path inventory still needs an audit before broad training.

## Artifacts

- Summary: `outputs/tables/g3i_cie_sipp_integration_summary.csv`
- Path parity: `outputs/tables/g3i_cie_sipp_path_parity.csv`
- Gate: `outputs/tables/g3i_cie_sipp_gate.csv`
- JSONL sample: `artifacts/teacher/legacy_astar/g3i_cie_sipp_integration_sample.jsonl`
- Figure: `outputs/figures/g3i_cie_sipp_integration.png`
