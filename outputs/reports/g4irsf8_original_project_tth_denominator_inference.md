# G4IRSF8 Original Project THT Denominator Inference

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

Aligned original output segments: 43603.
Closest denominator counts: `{'java_release_time_tth': 34300, 'ambiguous_equal': 165, 'original_entry_time_tth': 9138}`.
Decision: `release_denominator_supported`.

The original 2.5m/s text output stores per-segment start and finish time. Recomputing the published parsed mean from output start time matches the Java release/cur_time path-planning denominator, not the raw floating input pass_time for fractional and source-queued rows.
