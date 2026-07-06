# G4IRSF10 Plain Language Summary

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

当前 v2-safe 是最稳妥的 no-A* 工程候选：它使用 Java source queue/release 语义、baseline reservation 语义、Java release-time THT 分母，不依赖 v2-open 的 open-end 假设。

G4IRSF10 的主线不是马上训练大模型，而是先用 v2-safe 跑更大、更难、更长的工作流，暴露长尾、fallback、高源队列、fault/dynamic 等 hard cases。

这些 hard cases 会进入 v3 数据协议。下一步只允许轻量监督 candidate ranking、pairwise/listwise ranker、tiny/calibrated MLP 和 risk head；PPO/MAPPO/GNN/Transformer/full RL 暂时关闭。

G4J 仍然关闭。Java/CIE baseline 继续推进，但在 paper-protocol 边界完全打开前，不能把当前结果说成最终替代原始 Java/CIE/HCA*。
