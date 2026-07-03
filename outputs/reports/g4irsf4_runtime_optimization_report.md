# G4IRSF4 Runtime Optimization Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

| Item | Status | Notes |
| --- | --- | --- |
| avoid_pybind_huge_payload | IMPLEMENTED | Python no longer passes 348824 route tuples through pybind. |
| summary_only_streaming | IMPLEMENTED | Keeps loop autopsy possible without materializing all task rows in Python. |
| reservation_lookup | IMPLEMENTED | This optimization was required for full continuous state to return without changing policy behavior. |
| loop_cycle_detection_cache | PARTIAL | Full promotion requires full-manifest variant run. |
| edge_overlap_fast_path | BOUNDARY_HELD | Continuous row records whether diagnostic was enabled. |
| full_edge_overlap_diagnostic | BLOCKED | Full continuous planning result is still measured separately from this diagnostic. |

Continuous replay tasks/second: `1335.48694373`.
