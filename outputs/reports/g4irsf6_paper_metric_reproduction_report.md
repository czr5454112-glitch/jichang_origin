# G4IRSF6 Paper Metric Reproduction Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Scope | Metric | Paper | Original | No-A* | Claim |
| --- | --- | --- | --- | --- | --- |
| Table 5.2 speed sweep | THT min at 1.5 m/s | 5.1 | 5.1 | 5.088888888888687 | False |
| Table 5.2 speed sweep | THT mean at 1.5 m/s | 6.44 | 6.436670057765617 | 6.200586929552197 | False |
| Table 5.2 speed sweep | THT max at 1.5 m/s | 9.68 | 9.683333333333334 | 11.027780044445414 | False |
| Table 5.2 speed sweep | THT min at 2.0 m/s | 3.87 | 3.8666666666666667 | 3.8666666666666667 | False |
| Table 5.2 speed sweep | THT mean at 2.0 m/s | 4.93 | 4.936789330901097 | 4.811505480172296 | False |
| Table 5.2 speed sweep | THT max at 2.0 m/s | 7.37 | 7.366666666666666 | 8.835378350000791 | False |
| Table 5.2 speed sweep | THT min at 2.5 m/s | 3.13 | 3.1333333333333333 | 3.133333333333212 | False |
| Table 5.2 speed sweep | THT mean at 2.5 m/s | 3.96 | 3.9671227110082086 | 3.97610989127695 | False |
| Table 5.2 speed sweep | THT max at 2.5 m/s | 5.98 | 5.983333333333333 | 7.796669066667346 | False |
| Table 5.2 speed sweep | THT min at 3.0 m/s | 2.63 | 2.6333333333333333 | 2.638888888888808 | False |
| Table 5.2 speed sweep | THT mean at 3.0 m/s | 3.37 | 3.372953062513155 | 3.4183091829318957 | False |
| Table 5.2 speed sweep | THT max at 3.0 m/s | 5.05 | 5.05 | 7.138891472222895 | False |
| Table 5.3 baseline comparison | dispersed heuristic mean THT at 2.5 m/s | 4.43 | project xlsx artifact available; not executable rerun | 3.97610989127695 | False |
| Table 5.3 primary method | IoT-DRPA/HCA* mean THT at 2.5 m/s | 3.96 | 3.96712271 | 3.97610989127695 | False |
| No-A* quality sweep | best safe no-A* variant mean THT | 3.96 | 3.96712271 | 3.973867643580732 | False |
| TH / throughput | daily baggage throughput | 28506 | 28506 | 28506 | False |
| Table 5.4 dynamic/static | 1.5 m/s 10% deviation dynamic/static mean THT | dynamic=6.45; static=6.59 | blocked_full_java_runtime | 6.819314519743213 | False |
| Table 5.4 dynamic/static | 1.5 m/s 20% deviation dynamic/static mean THT | dynamic=6.67; static=6.86 | blocked_full_java_runtime | 7.5941060518336645 | False |
| Table 5.4 dynamic/static | 1.5 m/s 30% deviation dynamic/static mean THT | dynamic=6.91; static=7.11 | blocked_full_java_runtime | 8.602262937316157 | False |
| Table 5.4 dynamic/static | 2.0 m/s 10% deviation dynamic/static mean THT | dynamic=4.92; static=5.07 | blocked_full_java_runtime | 5.27341548347763 | False |

Matrix rows: 44. It covers THT min/mean/max at 1.5/2.0/2.5/3.0 m/s, TH, dispersed heuristic, IoT-DRPA/HCA*, dynamic/static deviation rows, and fault/interruption rows.
