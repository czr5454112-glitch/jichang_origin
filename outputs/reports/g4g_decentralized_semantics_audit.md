# G4G Decentralized Semantics Audit

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `7fdf7c0`
Contains G4F `7fdf7c0`: `True`
Dirty at runtime: `True`
Pushed to upstream at runtime: `False`

## Scope

Audit that runtime decisions use decentralized local information and do not consume teacher route suffixes or full CIE/A* as fallback.

## What Is Claimed

The selected runtime ladder uses the G4E small candidate scorer plus PIBT-lite local fallback; CIE/A* remains teacher/offline oracle only.

## What Is Not Claimed

The audit does not prove hardware conveyor spacing or edge capacity constraints; edge overlap remains diagnostic only.

## Repro Command

`python scripts/eval/run_g4g_no_astar_fallback_validation.py`

## Result Table

| Audit Item | Status | Details |
| --- | --- | --- |
| head_contains_g4f_commit | PASS | HEAD=7fdf7c0 contains 7fdf7c0: True |
| g4e_feature_names_exclude_forbidden_inputs | PASS | [] |
| model_manifest_lists_forbidden_inputs | PASS | ['full_cie_route_suffix', 'future_schedule', 'future_sipp_schedule', 'label_source', 'post_hoc_success', 'post_hoc_success_flag', 'route_finish_time', 'route_path', 'scenario', 'teacher_next_node', 'teacher_path'] |
| local_progress_fallback_source_no_teacher_or_astar | PASS | [] |
| g4f_config_runtime_full_astar_default_false | PASS | ['shared_g4e_small_mlp_candidate_scorer', 'risk_gated_local_progress_fallback', 'bounded_local_search_emergency_optional', 'full_cie_astar_emergency_disabled_in_g4f_audit'] |
| edge_capacity_primary_disabled | PASS | diagnostic_only |
| runtime_decision_allowed_inputs | PASS | current node, goal node, candidates, static map heuristic, current time, fault edges, local node-window reservations, local path history, deadline slack |

## Negative Findings

The script stores teacher paths only for audit comparison on the G4D planned scope, not as runtime decision input.

## Next Blocking Question

Can C++ runtime expose the same allowed input surface without accidentally adding teacher-route caches?
