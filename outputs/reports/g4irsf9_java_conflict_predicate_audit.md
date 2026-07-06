# G4IRSF9 Java Conflict Predicate Audit

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

Java predicate category: `java_closed_interval_conflict`.

| Line | Status | Supports | Interpretation |
| --- | --- | --- | --- |
| 255 | FOUND | java_closed_interval_conflict | Java separates intervals only when new_start > existing_end or new_end < existing_start; end==start is therefore a conflict. |
| 260 | FOUND | java_closed_interval_conflict | Java separates intervals only when new_start > existing_end or new_end < existing_start; end==start is therefore a conflict. |
| 299 | FOUND | closed_or_unqualified_window | Java stores node reservations as t1/t2 endpoints; no epsilon or half-open flag is attached here. |
| 300 | FOUND | closed_or_unqualified_window | Java stores node reservations as t1/t2 endpoints; no epsilon or half-open flag is attached here. |
| 157 | FOUND | context | Evidence captured for context. |
| 145 | FOUND | release_semantics_only | Release/cur_time evidence is relevant to source queue but does not prove open-end reservation. |
| 93 | FOUND | context | Evidence captured for context. |
| 85 | FOUND | java_closed_interval_conflict | Java separates intervals only when new_start > existing_end or new_end < existing_start; end==start is therefore a conflict. |

The audited Java predicates use strict `>` and `<` to prove separation. Under that predicate, two intervals that only touch at an endpoint still conflict.
