# G4IRSF7 Release Semantics Variant Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
committed_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
remote_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Variant | Mean THT | Gap vs Original | Complete | Conflicts | Full A* | Status |
| --- | --- | --- | --- | --- | --- | --- |
| current_noastar_release | 3.97610989127695 | 0.008987181276950196 | 28506 | 0 | 0 | not_promoted |
| java_epoch_release_exact | 3.97867354390154 | 0.011550833901539992 | 28506 | 0 | 0 | not_promoted |
| java_stable_sort_release | 3.97610989127695 | 0.008987181276950196 | 28506 | 0 | 0 | not_promoted_noop_or_blocked |
| java_source_queue_one_per_epoch | 3.556593852974151 | -0.41052885702584874 | 28506 | 0 | 0 | candidate_noninferior_strict |
| java_source_queue_multi_release_if_pass_time_ready | 3.97867354390154 | 0.011550833901539992 | 28506 | 0 | 0 | not_promoted |
| java_source_service_time_zero_at_entry | 3.97610989127695 | 0.008987181276950196 | 28506 | 0 | 0 | not_promoted_noop_or_blocked |
| java_unfinished_retry_semantics | 3.97610989127695 | 0.008987181276950196 | 28506 | 0 | 0 | not_promoted_noop_or_blocked |
