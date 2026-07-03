# G4IRSF3 Wait Or Fail Semantics Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Decision Rules

| Case | Action | Success Claim? |
| --- | --- | --- |
| already_at_node18_static_fault_18_22 | FAIL_SAFE_OR_HOLD_AT_NODE | False |
| upstream_no_safe_candidate_visible | WAIT_AT_SOURCE_OR_UPSTREAM_RETRY | False |
| scheduled_repair_window_known_by_operations | WAIT_UNTIL_REPAIR_THEN_RETRY | diagnostic_only |
| unknown_repair_time | WAIT_WITH_MAX_HOLD_THEN_SAFE_FAIL | False |

Waiting is a safety action, not a hidden success. If repair time is unknown, the policy should hold only up to an operational budget and then report failure/no-path.
