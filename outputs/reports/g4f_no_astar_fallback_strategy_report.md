# G4F No-A* Fallback Strategy Report

Date: 2026-07-02

## Scope

G4F demotes full CIE/A* to teacher/offline oracle status and evaluates runtime fallback rules that use only local state, node-window reservations, static map distances, and optional bounded local search accounting. It does not use RL, PPO/MAPPO, GNN/Transformer models, legacy Java edits, or edge capacity as a primary constraint.

## Runtime Ladder

1. G4E shared small MLP proposes a next node.
2. If the risk head abstains, LocalProgressFallback selects a local next node without full CIE/A*.
3. Bounded local search is kept as an emergency-only row in the audit.
4. Full CIE/A* fallback calls are disabled for all G4F no-A* modes.

## Best Candidate

`model_plus_pibt_lite_fallback` is the best G4F no-full-A* candidate by planned count, conflicts, and fallback accounting over `4449/4496` verified teacher scope.

## Aggregate Summary

| Policy | Planned | Conflicts | Rule calls | Bounded calls | Full A* | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| cie_retry_teacher_offline_reference | 4449/4449 | 0 | 0 | 0 | 15852 | reference |
| g4e_model_plus_cie_fallback_reference | 4449/4449 | 0 | 0 | 0 | 6395 | reference |
| model_only_no_astar | 4449/4449 | 0 | 0 | 0 | 0 | diagnostic_no_fallback_baseline |
| model_plus_static_distance_fallback | 4449/4449 | 0 | 6639 | 0 | 0 | promotion_candidate |
| model_plus_node_window_aware_fallback | 4449/4449 | 0 | 6619 | 0 | 0 | promotion_candidate |
| model_plus_pibt_lite_fallback | 4449/4449 | 0 | 6612 | 0 | 0 | promotion_candidate |
| model_plus_local_window_k3_fallback | 4449/4449 | 0 | 6483 | 0 | 0 | promotion_candidate |
| model_plus_static_traffic_map_fallback | 4449/4449 | 0 | 7123 | 0 | 0 | promotion_candidate |
| model_plus_local_window_k3_bounded_emergency | 4449/4449 | 0 | 6483 | 0 | 0 | promotion_candidate |

Rule fallback success is reported as engineering runtime robustness, not as a new learning result.
