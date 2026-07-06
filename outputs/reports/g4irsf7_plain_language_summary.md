# G4IRSF7 Plain Language Summary

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
committed_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
remote_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

这轮先从工程口径抹半秒，不训练新模型，不改真实地图，不改 legacy Java。
主要发现是 source release/source queue 语义会显著影响 source_retry 长尾；尤其 Java 每个 source 每秒最多释放队首一个任务，而当前连续 JSONL replay 会把同一 source 同一 pass_time 的任务同时压入。
开区间/跳过 source reservation 可以消除 source_retry 计数，但不自动改善平均 THT；因此不能把它当胜利。
当前最好的安全工程候选是 `source_queue_plus_open_end`，但它只能进入 G4IRSF7-B 或 no-A* v2 候选讨论，不能直接宣称论文胜利，也不能打开 G4J。
所有候选必须继续保持 0 failure / 0 conflict / 0 full A*，并通过速度、故障、动态/静态回归。
