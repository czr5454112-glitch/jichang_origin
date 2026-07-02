# G4D Large-Window CIE Retry Teacher Dataset Report

Date: 2026-07-02

## Scope

G4D-A expands the verified G3k CIE/A* retry teacher to larger real inputdata windows. It does not use RL, GNN, Transformer models, or `edge_capacity=1` as a primary constraint. Edge overlap remains diagnostic only.

## Window Summary

| Window | Tasks | Planned | Conflicts | A* attempts | Context |
| --- | --- | --- | --- | --- | --- |
| g4d_first144_no_fault | 144 | 144 | 0 | 196 | no_fault |
| g4d_first256_no_fault | 256 | 256 | 0 | 334 | no_fault |
| g4d_first512_no_fault | 512 | 512 | 0 | 654 | no_fault |
| g4d_first1024_no_fault | 1024 | 1024 | 0 | 1519 | no_fault |
| g4d_offset512_512_high_density | 512 | 512 | 0 | 852 | no_fault |
| g4d_offset2048_1024_high_density | 1024 | 977 | 0 | 10970 | no_fault |
| g4d_offset64_static512 | 512 | 512 | 0 | 621 | static_fault |
| g4d_offset64_repair512 | 512 | 512 | 0 | 706 | repair_window |

## Aggregate

- Total window tasks: `4496`
- Planned by verified teacher: `4449/4496`
- Node-window conflicts: `0`
- Estimated original CIE retry A* attempts: `15852`
- MOVE interface slices: `39313`
- Source retry slices: `962`
- Manifest rows, including negative outcomes: `4496`

## Negative Results

| Window | Unplanned | Decision |
| --- | --- | --- |
| g4d_offset2048_1024_high_density | 47 | preserve_negative_inventory |

## Decision

G4D-A is usable for the downstream audit and small-model pass because all windows keep node-window conflicts at `0` and `edge_capacity=1` stays non-primary. The `g4d_offset2048_1024_high_density` window remains a negative teacher-capacity result under the recommended 60s retry horizon and must not be hidden.

## Artifacts

- Window index: `outputs/tables/g4d_window_index.csv`
- Teacher summary: `outputs/tables/g4d_large_window_teacher_summary.csv`
- Interface slices: `outputs/tables/g4d_interface_decision_slices.csv`
- Source retry slices: `outputs/tables/g4d_source_retry_slices.csv`
- Full manifest: `artifacts/teacher/legacy_astar/g4d_large_window_teacher_manifest.jsonl`
- Sample manifest: `artifacts/teacher/legacy_astar/g4d_large_window_teacher_sample.jsonl`
