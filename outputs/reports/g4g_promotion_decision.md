# G4G Promotion Decision

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `7fdf7c0`
Contains G4F `7fdf7c0`: `True`
Dirty at runtime: `True`
Pushed to upstream at runtime: `False`

## Scope

Decide whether G4G evidence is sufficient to proceed to G4H C++ runtime / pybind parity.

## What Is Claimed

Overall G4G gate: `PASS`.

## What Is Not Claimed

A PASS is not a paper claim and does not authorize RL, larger neural models, or changing original CIE/Java semantics.

## Repro Command

`python scripts/eval/run_g4g_no_astar_fallback_validation.py`

## Result Table

| Criterion | Status | Evidence |
| --- | --- | --- |
| teacher_planned_scope_success | PASS | 4449 |
| node_window_conflicts_zero | PASS | 0 |
| runtime_full_cie_astar_zero | PASS | 0 |
| forbidden_feature_audit_pass | PASS | ['PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS'] |
| beats_model_only_on_key_metric | PASS | route_exact 3097 vs 2850; wait 1.0732253753656846 vs 1.281377480557331 |
| beats_pibt_lite_only_on_key_metric | PASS | planned 4449 vs 582; loop_deadlock 0 vs 3867 |
| loop_deadlock_cases_zero | PASS | 0 |
| avg_no_progress_below_threshold | PASS | 0.49763991908294 |
| task_1024_windows_stable | PASS | 1024 stress rows |
| smoke_2048_4096_no_catastrophic_failure | PASS | 2048/4096 smoke |
| teacher_no_path_boundary_preserved | PASS | 47 |
| overall_g4g_gate | PASS | recommend G4H C++ runtime |

## Negative Findings

Remote pushed state at runtime: `False`. Teacher no-path boundary rows remain `47`.

## Next Blocking Question

Proceed to G4H only if the local commit is pushed or the generated artifacts are reviewed locally.
