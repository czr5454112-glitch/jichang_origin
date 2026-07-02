# G4G Policy Ablation Report

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `7fdf7c0`
Contains G4F `7fdf7c0`: `True`
Dirty at runtime: `True`
Pushed to upstream at runtime: `False`

## Scope

Compare model-only, rule-only, model+rule fallback, and bounded local-search variants on the G4D verified teacher planned scope.

## What Is Claimed

Ablation separates model contribution from rule fallback contribution.

## What Is Not Claimed

Rule-only diagnostic rows are not promoted as the final learned policy, even if they reach many tasks.

## Repro Command

`python scripts/eval/run_g4g_no_astar_fallback_validation.py`

## Result Table

| Policy | Planned | Route Exact | Mean Wait | Loops | Decision Role |
| --- | --- | --- | --- | --- | --- |
| model_only_no_astar | 4449 | 2850 | 1.281377480557331 | 0 | diagnostic_model_only |
| pibt_lite_only | 582 | 261 | 5.408294443243315 | 3867 | diagnostic_rule_only |
| static_distance_only | 582 | 263 | 20.42495892851716 | 3867 | diagnostic_rule_only |
| node_window_aware_only | 582 | 252 | 6.288982008763179 | 3867 | diagnostic_rule_only |
| model_plus_static_distance_fallback | 4449 | 3072 | 1.254469302990213 | 0 | candidate |
| model_plus_node_window_fallback | 4449 | 3096 | 1.079820911890756 | 0 | candidate |
| model_plus_pibt_lite_fallback | 4449 | 3097 | 1.0732253753656846 | 0 | candidate |
| model_plus_bounded_local_search_k2 | 4449 | 2826 | 1.07706701191239 | 0 | diagnostic_bounded_local |
| model_plus_bounded_local_search_k3 | 4449 | 2781 | 1.280006768037297 | 0 | diagnostic_bounded_local |
| model_plus_bounded_local_search_k5 | 4449 | 2852 | 0.8599309024496 | 0 | diagnostic_bounded_local |

## Negative Findings

Rule-only rows are intentionally retained as negative evidence: with the controlled 24-step diagnostic cap they planned only 582/4449 and exposed 3867 loop/deadlock failures. This supports the claim that the G4G result is not just a pure local rule.

## Next Blocking Question

Which parts of PIBT-lite should move into C++ first: wait scoring, slack scoring, or loop/backtrack penalty?
