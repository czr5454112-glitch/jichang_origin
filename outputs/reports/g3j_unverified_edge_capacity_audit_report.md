# G3j Unverified Edge-Capacity Constraint Audit

Date: 2026-07-02

## 1. Scope

G3j removes `edge_capacity=1` from the primary CIE/A* integration because the original Java project validates node time-window constraints and fault edges, not a single-occupancy conveyor-edge capacity rule. Edge capacity and merge groups are kept only as diagnostic stress columns.

## 2. Constraint model comparison

| Variant | Role | Planned | Node conflicts | Diagnostic edge overlaps | Diagnostic merge overlaps | Waited tasks |
| --- | --- | --- | --- | --- | --- | --- |
| cie_node_window_primary | primary_original_java_scope | 127/144 | 0 | 433 | 25 | 0 |
| cie_plus_edge_capacity1_diagnostic | diagnostic_unverified_edge_capacity | 132/144 | 0 | 0 | 8 | 92 |
| cie_plus_edge_capacity1_merge_diagnostic | diagnostic_previous_g3i_style | 132/144 | 0 | 0 | 0 | 91 |
| cie_plus_merge_group_diagnostic | diagnostic_unverified_merge_group | 129/144 | 0 | 348 | 0 | 18 |

Primary result: `127/144` planned, `0` original node-window conflicts, and `127/127` planned paths preserve CIE/A* exactly.

The old strict edge-capacity overlap count is still reported as a diagnostic (`433` in the primary row), but it is not counted as a primary conflict because that rule is not validated by the original Java/CIE code.

## 3. Gates

| Gate | Pass | Value | Decision |
| --- | --- | --- | --- |
| primary_scope_matches_original_java | True | edge=not_applied_original_cie_node_window_primary;merge=not_applied_original_java_primary | use_node_window_primary |
| primary_planned_count_gate | True | 127 | g4a_pilot_candidate_under_verified_scope |
| primary_node_window_conflicts_zero | True | 0 | validated_constraints_clean |
| primary_preserves_astar_path | True | 127/127 | path_effect_preserved |
| edge_capacity_demoted_to_diagnostic | True | 433 | do_not_use_edge_capacity1_as_primary_constraint |
| edge_capacity_changes_timing | True | primary=127;edge_diag=132;previous_style=132 | keep_as_optional_stress_only |
| remaining_cie_no_path_inventory | True | 17 | audit_no_path_before_broad_training |

## 4. Remaining CIE no-path inventory

| Scenario | Reason | Count |
| --- | --- | --- |
| legacy_first32 | legacy_astar_no_path | 1 |
| legacy_offset64_merge32 | legacy_astar_no_path | 8 |
| legacy_offset64_repair32 | legacy_astar_no_path | 8 |

## 5. Decision

Correction pass: the project should use CIE/A* node-window timing as the primary verified simulation scope. `edge_capacity=1` is demoted to optional stress testing and must not drive teacher labels or G4A gates unless separately validated against the physical ICS system.

## Artifacts

- Constraint comparison: `outputs/tables/g3j_constraint_model_comparison.csv`
- Primary path parity: `outputs/tables/g3j_primary_path_parity.csv`
- Primary unplanned inventory: `outputs/tables/g3j_primary_unplanned_inventory.csv`
- Gate: `outputs/tables/g3j_unverified_constraint_gate.csv`
- JSONL sample: `artifacts/teacher/legacy_astar/g3j_node_window_primary_sample.jsonl`
- Figure: `outputs/figures/g3j_constraint_model_comparison.png`
