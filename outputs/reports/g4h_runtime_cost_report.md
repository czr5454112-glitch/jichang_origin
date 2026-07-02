# G4H Runtime Cost Report

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `dc3891b`
Contains G4F/G4G: `True` / `True`
Pushed to upstream at runtime: `False`

## Scope

Report interface-level and task-level cost: model decisions, PIBT-lite fallback calls, full CIE/A* fallback calls, runtime seconds, and decisions per second.

## A* Accounting

| System | Scope | Full A* | Model Decisions | PIBT-lite Calls | Zero Full-A* Share |
| --- | --- | --- | --- | --- | --- |
| original_cie_retry_teacher | g4d_teacher_windows | 15852 | 0 | 0 | 0 |
| g4e_model_plus_cie_fallback_reference | g4d_teacher_planned_scope | 6395 |  | 0 | 0.01708249 |
| g4h_model_plus_pibt_lite_no_astar | g4h_stress_windows | 0 | 262188 | 59885 | 1 |

## Runtime Latency

| Stage | Seconds | Decisions | Dec/sec |
| --- | --- | --- | --- |
| g4g_python_repro | 0 |  |  |
| cpp_action_core_parity | 15.8939585 | 35235 | 2216.88008055 |
| g4h_raw_stress_python_loop | 0 | 262188 |  |
