# G4IRSF9 Plain Language Summary

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `3432ef51f97d15045ac02d8632aae97450e9ce1a`
committed_head_at_generation: `3432ef51f97d15045ac02d8632aae97450e9ce1a`
remote_head_at_generation: `3432ef51f97d15045ac02d8632aae97450e9ce1a`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false
real_inputdata_modified: false

source queue/release 语义和 Java release-time THT 分母已经比较有证据，因此本轮冻结一个不依赖 open-end 的保守 v2-safe。
v2-safe: `model_plus_pibt_lite_java_source_queue_v2_safe`, mean THT=3.556593852974151 min, claim_level=`paper_protocol_engineering_candidate`.
open-end proof category: `java_closed_interval_conflict`.
v2-open: `model_plus_pibt_lite_source_queue_open_end_v2`, mean THT=3.5467070090507438 min, claim_level=`engineering_enhancement_not_paper_candidate`.
当前 Java 谓词显示触边也会被视作冲突，所以 open-end 不能作为 paper-protocol claim 直接使用。
G4J 仍关闭；下一步是继续把 Java/CIE baseline 和 open-end 等价性证据做稳，而不是继续刷指标。
