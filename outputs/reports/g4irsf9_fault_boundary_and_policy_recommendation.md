# G4IRSF9 Fault Boundary and Policy Recommendation

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

Fault rows: 32.
Fault rows with failed segments by candidate: `{'model_plus_pibt_lite_java_source_queue_v2_safe': 14, 'model_plus_pibt_lite_source_queue_open_end_v2': 14}`.
Material regressions by candidate: `{}`.

v2-safe and v2-open are paper-main/no-fault THT candidates. Fault scenarios remain diagnostic and should use a separately justified fault-aware policy if the runtime is placed in fault mode.

Runtime switching to a future fault-aware policy may be reasonable engineering, but it is not mixed into the v2-safe paper-main candidate in this round.
