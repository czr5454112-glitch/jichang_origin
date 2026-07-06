# G4IRSF10 Fault Policy Branch Plan

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

v2-safe remains a no-fault/paper-main conservative candidate. Fault mode must be a separate branch and must not be mixed into the v2-safe paper-main claim.

| Candidate | Scope | Risk |
| --- | --- | --- |
| v2_safe_no_fault | paper-main no-fault conservative candidate | do not overclaim fault optimality |
| v2_safe_plus_fault_aware | engineering diagnostic with fault-aware fallback | requires separate A/B evidence |
| fault_specific_fallback | local reroute/hold policy for mapped fault arcs | must preserve no full A* runtime rule |
| fault_hold_or_reroute_local | local recovery under selected static/repair faults | must keep fault rows separate from paper THT |
