# G4IRSF10 v2-safe Paper Protocol Repeat Report

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

Repeat x5 deterministic: `True`.
Repeat means: `[3.556593853, 3.556593853, 3.556593853, 3.556593853, 3.556593853]`.

| Scenario | Mean | Complete | Failed | Conflicts | Full A* |
| --- | --- | --- | --- | --- | --- |
| paper_main_2_5_repeat_1 | 3.556593852974151 | 28506 | 0 | 0 | 0 |
| paper_main_2_5_repeat_2 | 3.556593852974151 | 28506 | 0 | 0 | 0 |
| paper_main_2_5_repeat_3 | 3.556593852974151 | 28506 | 0 | 0 | 0 |
| paper_main_2_5_repeat_4 | 3.556593852974151 | 28506 | 0 | 0 | 0 |
| paper_main_2_5_repeat_5 | 3.556593852974151 | 28506 | 0 | 0 | 0 |

The speed sweep, dynamic/static 12 rows, and fault 16 diagnostics are retained in the CSV. Fault rows remain diagnostic and do not alter the v2-safe no-fault paper-main claim.
