# G3h CIE Backpressure / Pre-Reservation Audit

Date: 2026-07-02

## 1. Scope

G3h keeps the original CIE/Legacy A* project as the teacher source. No non-CIE planner is used to produce teacher labels. The audit asks whether the CIE route can be wrapped with upstream waiting or CIE-sourced upstream reroute labels so the runtime hard shield is still respected.

## 2. Recovery projection

| Projection | Added | Planned | Gate | Raw CIE conflicts |
| --- | --- | --- | --- | --- |
| g3f_best_current | 0 | 96 | False | 458 |
| cie_preserve_edge_backpressure | 21 | 117 | True | 458 |
| cie_backpressure_plus_cie_upstream_reroute | 23 | 119 | True | 458 |
| cie_no_path_remaining_inventory | 3 | 119 | True | 458 |

Unique G3g blocked scenario-task cases: `26`. CIE same-edge upstream waits: `21`. CIE upstream reroute cases: `2`. CIE no-path cases: `3`.

## 3. What this means

If we only keep the exact CIE bottleneck edge and add upstream wait labels, the projection is `117/144`, already above the `115/144` planned-count gate. If we also accept CIE's own upstream reroute path where CIE changes the route before the bottleneck, the projection is `119/144`.

This is still not a training green light, because raw CIE node-window routes create real edge/merge conflicts if executed blindly. The next step is to implement a closed-loop CIE backpressure replay that keeps the hard runtime shield active.

## 4. Label classes

| Class | Rows |
| --- | --- |
| cie_preserve_edge_upstream_wait | 24 |
| cie_no_path_still_blocked | 3 |
| cie_upstream_reroute_before_bottleneck | 2 |

## 5. Decision

Diagnostic pass: CIE remains the teacher source. The evidence says an upstream-wait wrapper around the original CIE route is the right next move, not a non-CIE teacher and not RL yet.

## Artifacts

- Candidate labels: `outputs/tables/g3h_cie_backpressure_candidate_labels.csv`
- Projection: `outputs/tables/g3h_cie_recovered_capacity_projection.csv`
- CIE path alignment: `outputs/tables/g3h_cie_path_alignment.csv`
- CIE upstream wait windows: `outputs/tables/g3h_cie_upstream_wait_windows.csv`
- Next gate: `outputs/tables/g3h_next_step_gate.csv`
- JSONL sample: `artifacts/teacher/legacy_astar/g3h_cie_backpressure_teacher_sample.jsonl`
- Projection figure: `outputs/figures/g3h_cie_backpressure_projection.png`
