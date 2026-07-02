# G4D True Closed-Loop and A* Cost Report

Date: 2026-07-02

## Scope

This is a route-exact learner closed-loop and A* call accounting audit over the G4D large-window teacher slices. It does not use RL, GNN, Transformer models, or `edge_capacity=1` as a primary constraint.

## Policy Comparison

| Policy | Planned | Conflicts | Fallback A* | Original A* | A* Reduction | Wrong High-conf |
| --- | --- | --- | --- | --- | --- | --- |
| cie_retry_teacher_baseline | 4449/4496 | 0 | 15852 | 15852 | 0.0 | 0 |
| g4b_no_calibration_large_window | 3728/4496 | 0 | 0 | 15852 | 1.0 | 837 |
| g4c_cluster_abstain_large_window | 4289/4496 | 0 | 2982 | 15852 | 0.811884935654807 | 171 |
| g4d_enhanced_mlp_risk_head | 4449/4496 | 0 | 6786 | 15852 | 0.5719152157456473 | 0 |
| shortest_time_heuristic_large_window | 263/4496 | 0 | 0 | 15852 | 1.0 | 5445 |
| fallback_only_per_interface | 4449/4496 | 0 | 39313 | 15852 | -1.4800025233409033 | 0 |

## G4D Result

G4D planned `4449/4496` under the verified teacher window scope, keeps node-window conflicts at `0`, and reduces verified CIE/A* calls from `15852` to `6786` (`0.572` reduction).

The high-density `g4d_offset2048_1024_high_density` teacher window still has unplanned CIE retry rows under the 60s retry horizon. G4D preserves that negative result rather than claiming a full 4496/4496 replacement.

## Scaling

| Window | Size | G4D Planned | Fallback Rate | A* Reduction | Decision |
| --- | --- | --- | --- | --- | --- |
| g4d_first1024_no_fault | 1024 | 1024 | 0.1615523465703971 | 0.057274522712310705 | pass_window |
| g4d_first144_no_fault | 144 | 144 | 0.16459884201819686 | -0.015306122448979664 | safety_pass_but_astar_regression |
| g4d_first256_no_fault | 256 | 256 | 0.1642624476500698 | -0.05688622754491024 | safety_pass_but_astar_regression |
| g4d_first512_no_fault | 512 | 512 | 0.16009445100354192 | -0.03669724770642202 | safety_pass_but_astar_regression |
| g4d_offset2048_1024_high_density | 1024 | 977 | 0.21383712550190467 | 0.810665451230629 | negative_teacher_window_preserved |
| g4d_offset512_512_high_density | 512 | 512 | 0.1634199134199134 | 0.113849765258216 | pass_window |
| g4d_offset64_repair512 | 512 | 512 | 0.15712290502793297 | 0.0439093484419264 | pass_window |
| g4d_offset64_static512 | 512 | 512 | 0.14596640643482375 | 0.006441223832528209 | pass_window |

## Decision

G4D passes the safety and aggregate-cost gate for moving to G4E/C++ runtime evaluation: it covers 512-task windows plus 1024-task smoke windows, keeps node-window conflicts at `0`, keeps edge capacity non-primary, avoids wrong high-confidence actions with the risk head, and reduces total verified CIE/A* calls. It is still not a paper-grade final replacement because one high-density 1024 window exposes teacher no-path rows under the current retry horizon, and several small windows have per-window A* call regressions because calibrated fallback is conservative.

## Artifacts

- Closed-loop summary: `outputs/tables/g4d_closed_loop_summary.csv`
- A* accounting: `outputs/tables/g4d_astar_call_accounting.csv`
- Fallback by window: `outputs/tables/g4d_fallback_rate_by_window.csv`
- Learner failures: `outputs/tables/g4d_learner_visited_failures.csv`
- Scaling: `outputs/tables/g4d_large_window_scaling.csv`
