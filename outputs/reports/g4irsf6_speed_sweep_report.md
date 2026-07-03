# G4IRSF6 Speed Sweep Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Speed | Paper Mean | Original Mean | No-A* Mean | No-A* Delta vs Paper | Claim |
| --- | --- | --- | --- | --- | --- |
| 1.5 | 6.44 | 6.436670057765617 | 6.200586929552197 | -0.23941307044780302 | False |
| 2.0 | 4.93 | 4.936789330901097 | 4.811505480172296 | -0.11849451982770365 | False |
| 2.5 | 3.96 | 3.9671227110082086 | 3.97610989127695 | 0.016109891276950172 | False |
| 3.0 | 3.37 | 3.372953062513155 | 3.4183091829318957 | 0.04830918293189557 | False |

All no-A* rows are generated from temporary speed-specific map artifacts under `artifacts/maps/g4irsf6/`. `data/processed/maps/map2.json` remains unchanged.
