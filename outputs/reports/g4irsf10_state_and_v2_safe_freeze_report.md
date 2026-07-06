# G4IRSF10 State and v2-safe Freeze Report

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

Frozen v2-safe policy: `model_plus_pibt_lite_java_source_queue_v2_safe`.
Frozen mean THT: `3.556593852974151` minutes.
Frozen model hash: `4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca`.

| Audit | Status | Details |
| --- | --- | --- |
| head_is_g4irsf9_or_descendant | PASS | G4IRSF10 starts from the pushed G4IRSF9 branch or a descendant. |
| v2_safe_bundle_exists_and_frozen | PASS | C:\PROGRAMING\czr005\artifacts\policies\g4irsf9_noastar_v2_safe_policy_bundle.json |
| v2_open_kept_separate | PASS | C:\PROGRAMING\czr005\artifacts\policies\g4irsf9_noastar_v2_open_policy_bundle.json |
| legacy_map_inputdata_clean | PASS | Protected legacy Java, real map2.json, and real inputdata.jsonl are unchanged. |

G4IRSF10 does not reopen v2-open as a paper candidate and does not train a new model in this pass.
