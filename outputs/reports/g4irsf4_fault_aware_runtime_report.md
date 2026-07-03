# G4IRSF4 Fault-Aware Runtime Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

## Runtime Variant

`model_plus_pibt_lite_fault_aware_v1` is wired into the C++ runtime with fallback `fault_aware_node_window_pibt_lite`. It uses only local topology, current fault edges/windows, current task path, and node-window reservations.

## No-Fault Guard

| Policy | Planned | Failed | Conflicts | Full A* |
| --- | --- | --- | --- | --- |
| model_plus_pibt_lite | 8192 | 0 | 0 | 0 |
| model_plus_pibt_lite_fault_aware_v1 | 8192 | 0 | 0 | 0 |

Subset scenarios are measured explicitly. The report does not claim a full-manifest fault-aware promotion beyond the measured scope.
