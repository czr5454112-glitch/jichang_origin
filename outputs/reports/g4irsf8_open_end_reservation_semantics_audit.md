# G4IRSF8 Open-End Reservation Semantics Audit

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

Decision: `engineering_reasonable_but_not_java_proven`.

| Evidence | Status | Claim Effect |
| --- | --- | --- |
| cpp_open_end_boundary | ENGINEERING_REASONABLE | May be valid physical semantics, but must be separately proven against Java before paper promotion. |
| java_conflict_condition | JAVA_CLOSED_INTERVAL_EVIDENCE | Open-end boundary is not Java-proven. |
| java_constraint_storage | EVIDENCE_CAPTURED | No explicit [start,end) epsilon rule found. |
| source_service_time_zero | NOT_PROVEN | Keep source service/reservation semantics in engineering candidate boundary. |

The open-end boundary is a reasonable engineering interpretation of handoff timing, but the original Java conflict predicate audited here does not prove it. Therefore `source_queue_plus_open_end` stays pending for paper-protocol promotion.
