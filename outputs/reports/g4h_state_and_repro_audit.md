# G4H State And Repro Audit

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `dc3891b`
Contains G4F/G4G: `True` / `True`
Pushed to upstream at runtime: `False`

## Scope

Re-run G4G locally and record git/legacy state. This does not claim remote verification when the local HEAD is not pushed.

## Result Table

| Policy | Planned | Conflicts | Full A* | Rule-only planned | Gate |
| --- | --- | --- | --- | --- | --- |
| model_plus_pibt_lite_fallback | 4449/4449 | 0 | 0 | 582 | PASS |

## Negative Findings

Remote pushed state at runtime: `False`. Legacy diff files: ``.
