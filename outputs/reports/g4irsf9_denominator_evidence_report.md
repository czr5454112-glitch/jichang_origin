# G4IRSF9 Denominator Evidence Report

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

G4IRSF8 already established majority support for Java release/cur_time denominator. G4IRSF9 expands that evidence by source, segment type, early-bag split, and pass-time integrality.

| Source | Total | Release | Entry | Entry Share |
| --- | --- | --- | --- | --- |
| 0 | 3200 | 1202 | 1996 | 0.62375 |
| 5 | 4886 | 3137 | 1749 | 0.3579615227179697 |
| 1 | 3193 | 1685 | 1505 | 0.4713435640463514 |
| 4 | 4887 | 3386 | 1501 | 0.30714139553918557 |
| 53 | 4254 | 2832 | 1422 | 0.3342736248236953 |
| 3 | 4887 | 4362 | 525 | 0.10742786985880909 |
| 2 | 3199 | 2759 | 440 | 0.13754298218193187 |
| 52 | 15097 | 14937 | 0 | 0.0 |

The original-entry votes concentrate in categories where output start time is an integer epoch while raw pass_time can be fractional or rounded nearby. They do not overturn the majority release-denominator evidence, but they are retained as a boundary instead of being hidden.
