# G4IR2 Learning Policy Contribution Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `5d4be59`
Upstream: `origin/codex/czr005-rewrite`
Upstream HEAD: `5d4be59`

## Quality

| Policy | Planned | Conflicts | Full A* | Fallback Share | Route Match |
| --- | --- | --- | --- | --- | --- |
| model_only_no_astar | 4449/4449 | 0 | 0 | 0.0 | 0.6405933917734322 |
| pibt_lite_only | 582/4449 | 0 | 0 | 1.0 | 0.05866486850977748 |
| model_plus_pibt_lite | 4449/4449 | 0 | 0 | 0.158004158004158 | 0.6961114857271297 |
| model_plus_static_distance_fallback | 4449/4449 | 0 | 0 | 0.1584449058495024 | 0.6904922454484154 |
| model_plus_node_window_greedy | 4449/4449 | 0 | 0 | 0.15811853515205085 | 0.6958867161159811 |
| model_plus_k_step_local_window | 4449/4449 | 0 | 0 | 0.1506283390651699 | 0.6250842886041807 |
| model_plus_pibt_lite_risk_abstain_off | 4449/4449 | 0 | 0 | 0.0 | 0.6405933917734322 |
| model_plus_pibt_lite_no_historical_risk | 4449/4449 | 0 | 0 | 0.12806236080178174 | 0.6961114857271297 |
| model_plus_pibt_lite_no_bottleneck_risk | 4449/4449 | 0 | 0 | 0.158004158004158 | 0.6961114857271297 |
| model_plus_pibt_lite_margin_only | 4449/4449 | 0 | 0 | 0.04574260643483913 | 0.6961114857271297 |

The ablation table separates model-only, rule-only, model plus local fallback, and risk-gate variants. No PPO/MAPPO/GNN/Transformer training is introduced in G4IR2.
