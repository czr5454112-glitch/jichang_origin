# G4IRSF6 Dynamic/Static Protocol Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Speed | Deviation | Paper Dynamic | Paper Static | No-A* Diagnostic | Claim |
| --- | --- | --- | --- | --- | --- |
| 1.5 | 10 | 6.45 | 6.59 | 6.819314519743213 | False |
| 1.5 | 20 | 6.67 | 6.86 | 7.5941060518336645 | False |
| 1.5 | 30 | 6.91 | 7.11 | 8.602262937316157 | False |
| 2.0 | 10 | 4.92 | 5.07 | 5.27341548347763 | False |
| 2.0 | 20 | 5.16 | 5.36 | 5.853669781953213 | False |
| 2.0 | 30 | 5.42 | 5.62 | 6.597805011386188 | False |
| 2.5 | 10 | 3.99 | 4.19 | 4.3461840994886405 | False |
| 2.5 | 20 | 4.25 | 4.46 | 4.811505480172296 | False |
| 2.5 | 30 | 4.49 | 4.72 | 5.405986800194808 | False |
| 3.0 | 10 | 3.39 | 3.56 | 3.728467190202629 | False |
| 3.0 | 20 | 3.51 | 3.72 | 4.115899964050722 | False |
| 3.0 | 30 | 3.64 | 3.87 | 4.612167447860613 | False |

The paper table compares dynamic IoT-DRPA and static LRA* under a deviation protocol. G4IRSF6 keeps that separate from no-A* effective-speed diagnostics and static A* lower bounds.
