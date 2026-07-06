# G4IRSF8 THT Denominator Audit

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

G4IRSF8 recomputes the same runtime traces under three denominators. This prevents a release-time improvement from being reported as a paper win unless the original project uses the same denominator.

| Variant | Denominator | Mean | Delta | Claim | Notes |
| --- | --- | --- | --- | --- | --- |
| java_source_queue_one_per_epoch | original_entry_time_tth | 4.124305453486908 | 0.1571827434869082 | False | not the denominator supported by original project output inference |
| java_source_queue_one_per_epoch | java_release_time_tth | 3.556593852974151 | -0.41052885702584874 | True | source queue release denominator matches original project output inference |
| java_source_queue_one_per_epoch | processed_segment_attempt_time_tth | 3.556593852974151 | -0.41052885702584874 | False | not the denominator supported by original project output inference |
| source_queue_plus_open_end | original_entry_time_tth | 4.114418609563502 | 0.14729589956350164 | False | not the denominator supported by original project output inference |
| source_queue_plus_open_end | java_release_time_tth | 3.5467070090507438 | -0.4204157009492562 | False | open-end reservation is engineering-reasonable but not Java-proven |
| source_queue_plus_open_end | processed_segment_attempt_time_tth | 3.5467070090507438 | -0.4204157009492562 | False | not the denominator supported by original project output inference |
| original_project_text_result | original_entry_time_tth | 5.764936746096144 | 1.7978140360961437 | True | baseline text result; not a no-A* promotion claim |
| original_project_text_result | java_release_time_tth | 5.197225145583386 | 1.2301024355833858 | True | baseline text result; not a no-A* promotion claim |
| original_project_text_result | processed_segment_attempt_time_tth | 3.9671227110082086 | 1.0082086276952396e-09 | True | baseline text result; not a no-A* promotion claim |

Original-project denominator inference status: `release_denominator_supported`.
Open-end reservation status: `engineering_reasonable_but_not_java_proven`.
