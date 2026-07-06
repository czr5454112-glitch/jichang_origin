# G4IRSF7 Source Retry Tail Report

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

Source-retry bags: 14895.

## Source Concentration

| Source | Count |
| --- | --- |
| 53|52 | 3776 |
| 3|52 | 2281 |
| 5|52 | 2236 |
| 4|52 | 2191 |
| 0|52 | 1502 |
| 1|52 | 1473 |
| 2|52 | 1436 |

Top 100 slow positive source-retry rows cover 7 source signatures.
Top 500 slow positive source-retry rows cover 7 source signatures.

The long tail is dominated by source/release timing and source queue concentration, not a broad median slowdown.
