# G4H Hidden Leakage Audit

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `dc3891b`
Contains G4F/G4G: `True` / `True`
Pushed to upstream at runtime: `False`

## Scope

Audit that model/fallback runtime does not consume teacher_next, teacher path, full route suffix, future schedule, post-hoc success, scenario lookup, or full CIE/A* result.

## Result Table

| Check | Status | Details |
| --- | --- | --- |
| head_contains_g4f_and_g4g | PASS | contains_g4f=True; contains_g4g=True |
| legacy_java_no_diff | PASS |  |
| g4e_feature_names_no_forbidden_inputs | PASS | [] |
| cpp_g4h_decision_core_no_astar_or_teacher_route | PASS | C++ G4H action core consumes feature rows, risk scalars, candidate ids, and local fallback components only. |
| runtime_full_cie_astar_default | PASS | disabled; C++ G4H action core reports runtime_full_cie_astar_calls=0 |
| edge_capacity_primary | PASS | False; node-window reservations remain primary, edge overlap diagnostic only |
| remote_verification_claim | PASS | head_pushed_to_upstream=False; reports mark local-only when false |
