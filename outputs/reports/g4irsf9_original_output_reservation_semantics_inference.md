# G4IRSF9 Original Output Reservation Semantics Inference

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

Original-output path category: `engineering_reasonable_but_unproven`.

| Scope | Reconstructable | Claim Effect |
| --- | --- | --- |
| original_output_columns | False | Original 2.5 output has task_id, start_node, output_start_time, finish_time only; it does not contain per-node route intervals. |
| start_node_whole_segment_proxy | True | This proxy treats an entire segment as occupying its start node, so it is intentionally not used to prove open-end semantics. |

Because the original text output does not store full per-node paths with t1/t2 intervals, B2 cannot prove `[start,end)` semantics from original output alone.
