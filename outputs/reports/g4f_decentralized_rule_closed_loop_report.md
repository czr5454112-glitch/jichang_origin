# G4F Decentralized Rule Closed-Loop Report

Date: 2026-07-02

## Scope

This is a learner-visited, goal-reaching closed loop over the eight G4D real inputdata windows. Node time windows remain the primary safety constraint; diagnostic edge overlap is not used as a failure criterion.

## Closed-Loop Results

| Policy | Planned | Route exact | Deviated success | Failures | Mean wait | Loops |
| --- | --- | --- | --- | --- | --- | --- |
| model_only_no_astar | 4449/4449 | 2850 | 1599 | 0 | 1.281377480557331 | 0 |
| model_plus_static_distance_fallback | 4449/4449 | 3072 | 1377 | 0 | 1.254469302990213 | 0 |
| model_plus_node_window_aware_fallback | 4449/4449 | 3096 | 1353 | 0 | 1.079820911890756 | 0 |
| model_plus_pibt_lite_fallback | 4449/4449 | 3097 | 1352 | 0 | 1.0732253753656846 | 0 |
| model_plus_local_window_k3_fallback | 4449/4449 | 2752 | 1697 | 0 | 1.5408949772980607 | 0 |
| model_plus_static_traffic_map_fallback | 4449/4449 | 2832 | 1617 | 0 | 0.9228917797253097 | 1508 |
| model_plus_local_window_k3_bounded_emergency | 4449/4449 | 2752 | 1697 | 0 | 1.5408949772980607 | 0 |

Original CIE retry teacher A* attempts: `15852`. G4F no-A* runtime modes use `0` full CIE/A* fallback calls.

## Failure Inventory

Failure inventory rows: `0`.
