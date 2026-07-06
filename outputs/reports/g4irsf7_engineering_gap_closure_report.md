# G4IRSF7 Engineering Gap Closure Report

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

| Combination | Mean | Gap | Complete | Conflicts | Full A* | Promotion |
| --- | --- | --- | --- | --- | --- | --- |
| official_baseline | 3.97610989127695 | 0.008987181276950196 | 28506 | 0 | 0 | not_promoted |
| route_quality_balanced | 3.974431057596331 | 0.007308347596330922 | 28506 | 0 | 0 | diagnostic_improvement_only |
| java_source_queue_one_per_epoch | 3.556593852974151 | -0.41052885702584874 | 28506 | 0 | 0 | candidate_noninferior_strict |
| open_end_boundary | 3.974268247409915 | 0.0071455374099151925 | 28506 | 0 | 0 | diagnostic_improvement_only |
| source_queue_plus_route_quality | 3.5564699086706097 | -0.4106528013293902 | 28506 | 0 | 0 | candidate_noninferior_strict |
| source_queue_plus_open_end | 3.5467070090507438 | -0.4204157009492562 | 28506 | 0 | 0 | candidate_noninferior_strict |
| source_queue_plus_open_end_plus_route_quality | 3.5480383077247075 | -0.4190844022752924 | 28506 | 0 | 0 | candidate_noninferior_strict |

Best stable engineering candidate: `source_queue_plus_open_end`.
G4J remains closed; this is an engineering non-inferiority candidate gate only.
