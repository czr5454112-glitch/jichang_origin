# G4F Large-Window Rule Stress Report

Date: 2026-07-02

## 1024-Task Windows

| Policy | Window | Planned | Conflicts | Rule calls | Full A* | Stable |
| --- | --- | --- | --- | --- | --- | --- |
| model_only_no_astar | g4d_first1024_no_fault | 1024/1024 | 0 | 0 | 0 | True |
| model_only_no_astar | g4d_offset2048_1024_high_density | 977/977 | 0 | 0 | 0 | True |
| model_plus_static_distance_fallback | g4d_first1024_no_fault | 1024/1024 | 0 | 1485 | 0 | True |
| model_plus_static_distance_fallback | g4d_offset2048_1024_high_density | 977/977 | 0 | 1811 | 0 | True |
| model_plus_node_window_aware_fallback | g4d_first1024_no_fault | 1024/1024 | 0 | 1481 | 0 | True |
| model_plus_node_window_aware_fallback | g4d_offset2048_1024_high_density | 977/977 | 0 | 1799 | 0 | True |
| model_plus_pibt_lite_fallback | g4d_first1024_no_fault | 1024/1024 | 0 | 1479 | 0 | True |
| model_plus_pibt_lite_fallback | g4d_offset2048_1024_high_density | 977/977 | 0 | 1796 | 0 | True |
| model_plus_local_window_k3_fallback | g4d_first1024_no_fault | 1024/1024 | 0 | 1337 | 0 | True |
| model_plus_local_window_k3_fallback | g4d_offset2048_1024_high_density | 977/977 | 0 | 2099 | 0 | True |
| model_plus_static_traffic_map_fallback | g4d_first1024_no_fault | 1024/1024 | 0 | 1397 | 0 | True |
| model_plus_static_traffic_map_fallback | g4d_offset2048_1024_high_density | 977/977 | 0 | 2594 | 0 | True |
| model_plus_local_window_k3_bounded_emergency | g4d_first1024_no_fault | 1024/1024 | 0 | 1337 | 0 | True |
| model_plus_local_window_k3_bounded_emergency | g4d_offset2048_1024_high_density | 977/977 | 0 | 2099 | 0 | True |

The high-density 1024 window keeps the inherited teacher boundary: the verified CIE teacher plans 977 of 1024 tasks under the current retry horizon, and G4F evaluates only that verified planned scope.

Bounded emergency accounting rows: `56`.
