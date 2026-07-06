# G4IRSF7 Reservation Semantics Report

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
| baseline_reservation | 3.97610989127695 | 0.008987181276950196 | 28506 | 0 | 0 | not_promoted |
| source_node_no_reservation | 3.974268247409915 | 0.0071455374099151925 | 28506 | 0 | 0 | diagnostic_improvement_only |
| source_node_zero_service | 3.97610989127695 | 0.008987181276950196 | 28506 | 0 | 0 | not_promoted_noop |
| entry_node_open_interval | 3.974268247409915 | 0.0071455374099151925 | 28506 | 0 | 0 | diagnostic_improvement_only |
| reservation_open_end_boundary | 3.974268247409915 | 0.0071455374099151925 | 28506 | 0 | 0 | diagnostic_improvement_only |
| storage_segment_independent_reservation | 3.974268247409915 | 0.0071455374099151925 | 28506 | 0 | 0 | diagnostic_improvement_only |
| java_service_time_parity | 3.97610989127695 | 0.008987181276950196 | 28506 | 0 | 0 | not_promoted_noop |
