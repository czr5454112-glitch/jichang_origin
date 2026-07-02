# G4E Fallback Reduction Audit Report

Date: 2026-07-02

## Scope

This audit explains the G4D fallback calls before any G4E recalibration. It uses the existing small MLP and risk head, does not use RL/GNN/Transformer, and keeps `edge_capacity=1` diagnostic-only.

## Fallback Ledger Summary

- Fallback calls: `6786`
- Fallbacks that prevented a wrong model action: `1771`
- Task groups with zero fallback: `0/4449`

## Top Nodes

| Node | Fallbacks | Would-be wrong | Unique tasks | Top reasons |
| --- | --- | --- | --- | --- |
| 22 | 1429 | 398 | 1429 | {'low_margin': 1429} |
| 11 | 1165 | 228 | 1165 | {'low_margin+historical_risk': 994, 'low_margin': 171} |
| 20 | 898 | 79 | 898 | {'low_margin': 898} |
| 16 | 670 | 412 | 670 | {'low_margin': 670} |
| 19 | 657 | 304 | 657 | {'low_margin+historical_risk': 603, 'low_margin': 54} |
| 6 | 489 | 196 | 489 | {'low_margin+historical_risk': 420, 'low_margin': 69} |
| 9 | 482 | 73 | 482 | {'low_margin': 482} |
| 31 | 254 | 5 | 254 | {'low_margin': 254} |
| 33 | 123 | 0 | 123 | {'low_margin': 123} |
| 36 | 122 | 6 | 122 | {'low_margin': 122} |

## Window Summary

| Window | Fallbacks | Rate | Would-be wrong | Unique tasks |
| --- | --- | --- | --- | --- |
| g4d_first1024_no_fault | 1432 | 0.1615523465703971 | 374 | 1024 |
| g4d_first144_no_fault | 199 | 0.16459884201819686 | 50 | 144 |
| g4d_first256_no_fault | 353 | 0.1642624476500698 | 80 | 256 |
| g4d_first512_no_fault | 678 | 0.16009445100354192 | 149 | 512 |
| g4d_offset2048_1024_high_density | 2077 | 0.21383712550190467 | 601 | 977 |
| g4d_offset512_512_high_density | 755 | 0.1634199134199134 | 225 | 512 |
| g4d_offset64_repair512 | 675 | 0.15712290502793297 | 165 | 512 |
| g4d_offset64_static512 | 617 | 0.14596640643482375 | 127 | 512 |

## Decision

Most G4D fallback calls are conservative rather than directly preventing wrong actions. This justifies G4E risk-threshold reduction, but only with a hard constraint that wrong high-confidence actions remain `0`.

## Artifacts

- Ledger: `outputs/tables/g4e_fallback_call_ledger.csv`
- By node: `outputs/tables/g4e_fallback_by_node.csv`
- By window: `outputs/tables/g4e_fallback_by_window.csv`
- By task: `outputs/tables/g4e_fallback_by_task.csv`
- Hardcase sample: `artifacts/teacher/legacy_astar/g4e_hardcase_teacher_sample.jsonl`
