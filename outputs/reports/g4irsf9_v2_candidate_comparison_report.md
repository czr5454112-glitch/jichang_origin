# G4IRSF9 v2 Candidate Comparison Report

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

Open-end proof category: `java_closed_interval_conflict`.

| Candidate | Mean | Complete | Failed | Claim |
| --- | --- | --- | --- | --- |
| model_plus_pibt_lite_java_source_queue_v2_safe | 3.556593852974151 | 28506 | 0 | paper_protocol_engineering_candidate |
| model_plus_pibt_lite_source_queue_open_end_v2 | 3.5467070090507438 | 28506 | 0 | engineering_enhancement_not_paper_candidate |

v2-safe is the conservative candidate: source queue release is supported, baseline reservation is retained. v2-open is faster but remains separated unless open-end is proven.
