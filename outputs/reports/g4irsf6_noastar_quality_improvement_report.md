# G4IRSF6 No-A* Quality Improvement Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
artifact_generation_head: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
committed_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
remote_head_at_generation: `de3e5e29b4fb35608d813bee0bedbafd7bae1679`
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Variant | Mean THT | Delta vs Official | Conflicts | Full A* | Decision |
| --- | --- | --- | --- | --- | --- |
| official_model_plus_pibt_lite | 3.97610989127695 | 0.0 | 0 | 0 | retain_baseline_equal |
| less_wait_penalty | 4.016054237377704 | 0.03994434610075359 | 0 | 0 | not_promoted_slower |
| more_goal_progress | 4.007301363452454 | 0.031191472175503776 | 0 | 0 | not_promoted_slower |
| less_fallback_when_model_confident | 3.985939441976245 | 0.00982955069929492 | 0 | 0 | not_promoted_slower |
| risk_margin_lower | 4.00561536439377 | 0.029505473116819836 | 0 | 0 | not_promoted_slower |
| risk_margin_higher | 3.97610989127695 | 0.0 | 0 | 0 | retain_baseline_equal |
| fallback_progress_guard | 4.007301363452454 | 0.031191472175503776 | 0 | 0 | not_promoted_slower |
| cycle_guard_light | 3.973867643580732 | -0.002242247696218058 | 0 | 0 | reject_unsafe_or_incomplete |
| route_quality_balanced | 3.974431057596331 | -0.0016788336806192738 | 0 | 0 | diagnostic_improvement_only |
| fault_aware_v1 | 3.988193743122827 | 0.012083851845877014 | 0 | 0 | not_promoted_slower |

Best numeric sweep row: `cycle_guard_light` mean=3.973867643580732 min. Promotion still requires the strict claim boundary; no variant may trade away node-window safety, complete bags, or zero full-CIE/A*.
