# G4IRSF4 Level B-Light Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

| Rule | Coverage | Ready? |
| --- | --- | --- |
| inputdata_queue_replay | PASS | True |
| early_bag_split | PASS | True |
| storage_in_out | PASS | True |
| pass_time_std_time_relation | PASS | True |
| source_queue_sort | PASS | False |
| epoch_release | B_LIGHT | True |
| active_original_high_flow_generator | FAIL | False |

Level B-light is plausible for inputdata queue/day scaling rules, but original active high-flow generation is still not claimed.
