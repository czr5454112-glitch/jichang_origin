# czr005 G3j Unverified Edge-Capacity Removal Plan

Date: 2026-07-02
Branch: `codex/czr005-rewrite`

## Scope

G3j corrects the project scope after identifying that `edge_capacity=1` is not validated by the original CIE/Legacy Java project.

The primary simulation scope should now be:

```text
Original CIE / Legacy A* route intent
+ Java-style node time-window constraints
+ fault-edge handling
```

Conveyor-edge single-occupancy capacity and merge-group capacity must be treated as optional diagnostics unless separately validated against the physical ICS system or the source paper.

## Required Work

- Change the path-constrained CIE/SIPP wrapper so it does not apply edge capacity by default.
- Keep explicit `edge_capacity=1` available only when a caller asks for a diagnostic stress run.
- Run the real `map2/inputdata` matched windows with:
  - primary original-Java scope,
  - optional merge-group diagnostic,
  - optional edge-capacity diagnostic,
  - previous G3i-style edge-capacity plus merge diagnostic.
- Report strict edge overlaps as diagnostics, not primary conflicts.
- Preserve original CIE/A* paths for all planned primary routes.

## Outputs

- `scripts/eval/run_g3j_remove_unverified_edge_capacity.py`
- `outputs/reports/g3j_unverified_edge_capacity_audit_report.md`
- `outputs/tables/g3j_constraint_model_comparison.csv`
- `outputs/tables/g3j_primary_path_parity.csv`
- `outputs/tables/g3j_primary_unplanned_inventory.csv`
- `outputs/tables/g3j_unverified_constraint_gate.csv`
- `artifacts/teacher/legacy_astar/g3j_node_window_primary_sample.jsonl`
- `outputs/figures/g3j_constraint_model_comparison.png`

## Gate

G3j passes if:

- the primary scope applies no edge-capacity or merge-group rule,
- primary planned count remains above `115/144`,
- original node-window conflicts are zero,
- all planned primary routes preserve the CIE/A* path,
- edge-capacity effects are explicitly labeled diagnostic only.

## Expected Next Step

Audit the remaining CIE/A* no-path rows under the verified node-window scope, then build any G4A pilot manifest from this corrected primary model.
