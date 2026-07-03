# G4IRSF6 THT Gap Autopsy Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

Rows: 28506 bags. Complete comparable bags: 28506.
Mean no-A* minus original-project delta: 0.539231 seconds.
Median delta: -0.800000 seconds.

## Delay Reason Counts

| Reason | Count |
| --- | --- |
| no_slower_or_faster | 16615 |
| source_retry | 9481 |
| extra_wait_due_to_node_reservation | 1871 |
| fallback_detour | 514 |
| loop_or_near_loop | 25 |

## Slowest Positive Deltas

| Task | Delta Seconds | Wait | Fallback | Reason |
| --- | --- | --- | --- | --- |
| 3357 | 204.6170670000538 | 156.01706700006253 | 5 | source_retry |
| 8875 | 204.12484200003382 | 158.1248420000411 | 4 | source_retry |
| 8848 | 201.3772300000419 | 155.37723000004917 | 4 | source_retry |
| 8830 | 200.2518750000345 | 149.4518750000425 | 3 | source_retry |
| 8841 | 198.50737900003878 | 152.50737900004606 | 4 | source_retry |
| 8891 | 192.02271100004145 | 142.42271100005019 | 5 | source_retry |
| 3456 | 190.88431600004697 | 163.68431600005715 | 5 | source_retry |
| 3478 | 186.8475520000502 | 192.44755200005602 | 4 | source_retry |
| 3437 | 186.59324400004334 | 187.19324400004916 | 3 | source_retry |
| 8765 | 184.40010900003108 | 109.0001090000369 | 6 | source_retry |

The main gap is small in aggregate, but it is not hidden: every bag keeps original-project THT, no-A* THT, route, wait, fallback, loop, and source-retry evidence.
