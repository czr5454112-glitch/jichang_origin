# G4IRSF4 State And Repro Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

## Git And Data State

| Check | Status | Details |
| --- | --- | --- |
| branch | PASS | current branch |
| head_contains_284475d | PASS | G4IRSF3 baseline must be an ancestor |
| remote_equal_local_at_start | PASS | Before new commit/push this should match upstream. |
| working_tree_clean_before_generation | INFO | The tree becomes dirty while G4IRSF4 artifacts are generated. |
| legacy_java_diff_empty | PASS | legacy Java and map files must stay read-only. |
| high_flow_jsonl_sha256 | PASS | g4irsf2_high_flow_tasks.jsonl hash vs manifest |
| high_flow_jsonl_line_count | PASS | full task stream must be present |

## Recent Log

```text
284475d eval: add g4irsf3 fault-aware full manifest audit
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
```

The high-flow JSONL is verified against the manifest. Legacy Java/map diff is checked separately and must remain empty.
