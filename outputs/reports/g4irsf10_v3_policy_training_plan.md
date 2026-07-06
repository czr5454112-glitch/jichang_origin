# G4IRSF10 v3 Policy Training Plan

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `b2e3d799a8107f06dfb97ef9e102b03f29503719`
committed_head_at_generation: `b2e3d799a8107f06dfb97ef9e102b03f29503719`
remote_head_at_generation: `b2e3d799a8107f06dfb97ef9e102b03f29503719`
policy_id: `model_plus_pibt_lite_java_source_queue_v2_safe`
release_semantics: `java_source_queue_one_per_epoch`
reservation_semantics: `baseline`
tth_denominator: `java_release_time_tth`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
v2_open_used_for_paper_claim: false
g4j_opened: false

| Model | Label | Benefit | Latency |
| --- | --- | --- | --- |
| v3_linear_ranker | pairwise_or_listwise_candidate_preference | lower fallback rate on high-flow tail without increasing conflicts | very_low |
| v3_tiny_mlp | supervised_candidate_ranking | better branch choice in high pressure source queues | low |
| v3_feature_pruned_mlp | supervised_candidate_ranking_with_feature_ablation | reduce overfit and improve explainability | low |
| v3_calibrated_margin_model | risk_calibration | abstain less on safe high-flow decisions while keeping zero wrong high-confidence target | very_low |
| v3_risk_head_plus_ranker | candidate_rank_and_abstain | reduce fallback, detours, and long tails in high-flow/fault diagnostics | medium |

The next stage is G4IRSF10-B: lightweight supervised/ranking policy training and A/B evaluation. PPO/MAPPO/GNN/Transformer/full RL remain closed.
