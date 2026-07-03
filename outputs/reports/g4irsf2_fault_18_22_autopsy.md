# G4IRSF2 Fault 18->22 Autopsy

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `dafc6e0`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample

## Failure Counts

| Scenario | Failure Rows |
| --- | --- |
| repair_18_22_8200_9000 | 32 |
| static_fault_18_22 | 1150 |

These rows use the fixed real map and no runtime full CIE/A* fallback. The 18->22 failure mode remains a real blocker to inspect, not a hidden success.
