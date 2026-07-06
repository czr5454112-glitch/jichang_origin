# G4IRSF7 THT Formula Audit

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

| Check | Status | Observed | Expected |
| --- | --- | --- | --- |
| original_text_result_exists | PASS | C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目\项目仿真（数据+分析）\仿真数据2\2.5 0.txt | readable |
| raw_inputdata_row_count | PASS | 28507 | 28507 |
| processed_segment_count | PASS | 43603 | 43603 |
| complete_bag_count | PASS | 28506 | 28506 |
| storage_dwell_excluded | PASS | segment duration sum only | exclude dwell between storage-in and storage-out |
| minutes_conversion | PASS | seconds / 60 | seconds / 60 |
| min_recompute | PASS | 3.1333333333333333 | 3.13333333 |
| mean_recompute | PASS | 3.9671227110082086 | 3.96712271 |
| max_recompute | PASS | 5.983333333333333 | 5.98333333 |
| rounding_precision | PASS | 8 decimal CSV precision after recompute | no pre-aggregation rounding |

The original-project 2.5m/s THT is reproduced before any policy or engineering variant is evaluated.
