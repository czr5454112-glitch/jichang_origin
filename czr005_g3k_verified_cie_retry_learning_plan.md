# czr005 G3k Verified CIE Retry Audit Plan

## Objective

Determine whether the `17` G3j primary no-path rows are true structural no-path cases or temporary current-time failures under the original Java `unfinishTasks` retry semantics.

This round is an audit and teacher-scope cleanup step. It must not train a model, start PPO/MAPPO, add GNN/Transformer work, broaden G4A, modify legacy Java, or promote `edge_capacity=1` into a primary constraint.

## Verified Scope

- Route source: original CIE/Legacy A* intent.
- Primary dynamic constraint: Java-style node time windows.
- Fault handling: static fault edges and currently active repair-window faults.
- Retry behavior: failed A* tasks remain in an unfinished queue and are retried at later scheduler times.
- Edge overlap: diagnostic only, never a primary conflict or teacher gate.

## Required Outputs

- `outputs/reports/g3k_cie_node_window_retry_audit_report.md`
- `outputs/tables/g3k_retry_summary.csv`
- `outputs/tables/g3k_no_path_retry_timeline.csv`
- `outputs/tables/g3k_recovered_no_path_cases.csv`
- `outputs/tables/g3k_remaining_no_path_cases.csv`
- `outputs/tables/g3k_java_semantics_alignment.csv`
- `outputs/tables/g3k_teacher_label_taxonomy.csv`
- `outputs/tables/g3k_edge_overlap_diagnostic_only.csv`
- `artifacts/teacher/legacy_astar/g3k_cie_retry_teacher_sample.jsonl`

## Decision Gate

If Java-style retry reaches at least `132/144` planned with `0` node-window conflicts, while still not using `edge_capacity=1` as a primary constraint, the project may proceed to a small G4A pilot dataset under verified CIE/Java retry semantics.

If it fails that gate, do not train. Continue auditing Java scheduler semantics.

## Actual Result

G3k reproduced G3j primary exactly at `127/144` planned with `0` node-window conflicts and `17` no-path rows. Java-style source retry recovered all `17/17` no-path rows and reached `144/144` planned with `0` node-window conflicts. Strict edge overlap rose to `556`, but remained diagnostic only.

The next permitted step is a G4A pilot dataset, not broad training.
