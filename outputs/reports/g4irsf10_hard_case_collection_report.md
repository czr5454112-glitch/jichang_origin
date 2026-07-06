# G4IRSF10 Hard-Case Collection Report

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

Hard cases written: `50000`.
Hard cases seen before cap: `5731536`.
Truncated by cap: `True`.

| Category | Count |
| --- | --- |
| model_vs_fallback_disagreement | 4708304 |
| edge_pressure_high | 3394996 |
| large_detour | 2999860 |
| fallback_high_frequency | 687520 |
| fault_failure | 335990 |
| p95_or_p99_delay | 272082 |
| high_tth_tail | 54179 |
| near_loop | 13573 |

Hard cases are collected from v2-safe paper, high-flow, dynamic, and fault diagnostics. The index is for v3 data preparation only; no new model is trained in G4IRSF10.

Source queue backlog is also retained at matrix level in `outputs/tables/g4irsf10_v2_safe_high_flow_matrix.csv`. It is not always a per-task `source_wait_seconds` field because the v2-safe denominator is Java release-time THT, so backlog pressure is carried into v3 data selection through the scenario rows and pressure reports rather than hidden.
