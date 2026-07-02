# G4F Fallback Ladder Ablation Report

Date: 2026-07-02

## Comparison

The ablation keeps the G4E model fixed and swaps only the runtime abstain handler. This separates model behavior from rule fallback behavior.

| Policy | Model decisions | Rule calls | Bounded calls | Full A* | Zero-full-A* tasks | Promotion |
| --- | --- | --- | --- | --- | --- | --- |
| model_only_no_astar | 34477 | 0 | 0 | 0 | 4449 | False |
| model_plus_static_distance_fallback | 28623 | 6639 | 0 | 0 | 4449 | True |
| model_plus_node_window_aware_fallback | 28623 | 6619 | 0 | 0 | 4449 | True |
| model_plus_pibt_lite_fallback | 28623 | 6612 | 0 | 0 | 4449 | True |
| model_plus_local_window_k3_fallback | 30403 | 6483 | 0 | 0 | 4449 | True |
| model_plus_static_traffic_map_fallback | 33481 | 7123 | 0 | 0 | 4449 | True |
| model_plus_local_window_k3_bounded_emergency | 30403 | 6483 | 0 | 0 | 4449 | True |

Bounded/local emergency rows are counted separately from full CIE/A* fallback. In this audit, full CIE/A* is not used by any no-A* mode.
