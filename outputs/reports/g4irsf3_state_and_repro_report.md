# G4IRSF3 State And Repro Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Git State

| Check | Status | Details |
| --- | --- | --- |
| branch | PASS | current local branch and tracking branch |
| head | INFO | 209f895 |
| head_contains_209f895 | PASS | G4IRSF2 commit must be an ancestor |
| head_is_ancestor_of_upstream | PASS | Before this run local should match upstream; after new commit it will become ahead until push. |
| working_tree_status_during_g4irsf3_generation | INFO | The tree is expected to become dirty while G4IRSF3 artifacts are generated or staged; legacy diff is checked separately. |
| legacy_java_diff_empty | PASS | legacy Java must stay read-only |
| g4irsf2_high_flow_tasks_jsonl_ignored | PASS | large JSONL is reproduced, not committed |
| g4irsf2_high_flow_tasks_jsonl_exists | PASS | reproduction script can regenerate it if missing |

## Recent Log

```text
209f895 eval: add g4irsf2 original ics high-flow audit
dafc6e0 eval: add g4ir2 runtime bottleneck audit
5d4be59 eval: add g4i full cpp runtime audit
b3d2296 eval: add g4h no-astar cpp runtime audit
dc3891b eval: add g4g no-astar fallback stress audit
7fdf7c0 eval: add g4f no-astar fallback audit
4599f9b eval: add g4e fallback reduction audit
597b9b9 eval: add g4d large-window runtime audit
678c169 eval: add g4c failure-driven aggregation
5d7ebad eval: add g4 cie retry policy pilot
6932244 eval: add g3k cie retry audit
1d49600 eval: demote unverified edge capacity constraint
3654568 eval: integrate cie path constrained sipp
c904205 eval: add g3h cie backpressure audit
769c2dc eval: add g3g scheduler semantics alignment
978e760 eval: add g3f edge capacity legacy scheduler audit
20b34d5 fix: repair downstream fault reachability semantics
3f9fd68 eval: add g3d legacy teacher wait audit
891b67c eval: add g3c legacy astar teacher audit
b8dac08 eval: add g3 oracle upper bound
```

The large high-flow task file remains ignored; the tracked manifest and G4IRSF3 reproduction script are the reproducibility boundary.
