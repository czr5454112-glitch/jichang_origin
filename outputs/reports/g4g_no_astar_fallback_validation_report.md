# G4G No-A* Fallback Validation Report

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `7fdf7c0`
Contains G4F `7fdf7c0`: `True`
Dirty at runtime: `True`
Pushed to upstream at runtime: `False`

## Scope

Validate G4F no-full-A* runtime fallback on the verified G4D teacher planned scope and additional raw inputdata stress windows. This run does not train RL/PPO/MAPPO, GNN, or Transformer models, does not edit legacy Java, and does not use edge capacity as a primary constraint.

## What Is Claimed

`model_plus_pibt_lite_fallback` reaches `4449/4449` within the verified teacher planned scope, keeps node-window conflicts at `0`, and uses `0` runtime full CIE/A* calls.

## What Is Not Claimed

This does not claim remote verification, paper-grade final replacement, or that the verified CIE teacher no-path boundary is solved as a teacher result.

## Repro Command

`python scripts/eval/run_g4g_no_astar_fallback_validation.py`

## Result Table

| Policy | Planned | Conflicts | Full A* | Rule Calls | Route Exact | Failures |
| --- | --- | --- | --- | --- | --- | --- |
| model_only_no_astar | 4449/4449 | 0 | 0 | 0 | 2850 | 0 |
| pibt_lite_only | 582/4449 | 0 | 0 | 98518 | 261 | 3867 |
| static_distance_only | 582/4449 | 0 | 0 | 97991 | 263 | 3867 |
| node_window_aware_only | 582/4449 | 0 | 0 | 98484 | 252 | 3867 |
| model_plus_static_distance_fallback | 4449/4449 | 0 | 0 | 6639 | 3072 | 0 |
| model_plus_node_window_fallback | 4449/4449 | 0 | 0 | 6619 | 3096 | 0 |
| model_plus_pibt_lite_fallback | 4449/4449 | 0 | 0 | 6612 | 3097 | 0 |
| model_plus_bounded_local_search_k2 | 4449/4449 | 0 | 0 | 7071 | 2826 | 0 |
| model_plus_bounded_local_search_k3 | 4449/4449 | 0 | 0 | 6964 | 2781 | 0 |
| model_plus_bounded_local_search_k5 | 4449/4449 | 0 | 0 | 6911 | 2852 | 0 |

## Negative Findings

Teacher no-path boundary rows remain separately recorded: `47`.

## Next Blocking Question

Can the selected policy be exported to C++ with Python/C++ parity and comparable per-decision latency?
