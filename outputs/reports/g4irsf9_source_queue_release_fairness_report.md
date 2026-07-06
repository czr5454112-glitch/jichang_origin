# G4IRSF9 Source Queue Release Fairness Report

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

Every source is audited for one-release-per-epoch behavior, backlog, and queue delay. Queue delay is excluded from `java_release_time_tth`; that exclusion is called out explicitly and tied to the original output denominator inference.

| Source | Tasks | Max/Epoch | Max Backlog | Total Queue Delay |
| --- | --- | --- | --- | --- |
| 52 | 15097 | 1 | 310 | 984466.0 |
| 3 | 4887 | 1 | 3 | 172.0 |
| 5 | 4886 | 1 | 3 | 172.0 |
| 4 | 4887 | 1 | 3 | 153.0 |
| 53 | 4254 | 1 | 3 | 146.0 |
| 0 | 3200 | 1 | 2 | 80.0 |
| 2 | 3199 | 1 | 3 | 80.0 |
| 1 | 3193 | 1 | 2 | 72.0 |
