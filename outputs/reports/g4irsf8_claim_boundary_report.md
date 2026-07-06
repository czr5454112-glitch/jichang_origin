# G4IRSF8 Claim Boundary Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `ab835c53e589fd8463675ea5901086f2f86a2648`
committed_head_at_generation: `ab835c53e589fd8463675ea5901086f2f86a2648`
remote_head_at_generation: `ab835c53e589fd8463675ea5901086f2f86a2648`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

分母审计支持原项目文本使用 Java release/cur_time 作为输出 THT 起点，因此 source queue 语义不是单纯偷换分母。但 open-end reservation 尚未被 Java 代码证明，只能冻结为工程候选，不能宣称论文级最终胜利。

Machine-readable conclusion: `source release denominator is supported by original project text, but open-end reservation is not Java-proven; source_queue_plus_open_end remains an engineering candidate pending open-end proof.`
Policy bundle claim_level: `engineering_candidate_pending_open_end_java_proof`

禁止事项保持关闭：不改 legacy Java、不改真实 map2.json、不训练新模型、不使用 runtime full CIE/A*、不使用 teacher/future schedule、不直接 G4J。
