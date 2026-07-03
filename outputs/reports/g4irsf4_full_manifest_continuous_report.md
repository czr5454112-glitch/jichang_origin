# G4IRSF4 Full-Manifest Continuous Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

## Result

| Tasks | Planned | Failed | Failed Reasons | Conflicts | Full A* | Elapsed s | Continuous? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 348824 | 348824 | 0 | {} | 0 | 0 | 261.196 | True |

This is one C++ replay call over the JSONL task file. Reservation and traffic memory are not reset between chunks because no chunks are used.

Edge diagnostic blocker note: `full_edge_overlap_diagnostic_attempt_exceeded_1700_cpu_seconds_without_returning_binary_reservation_lookup_optimized`.

If this continuous result is worse than the previous chunked G4IRSF3 result, that is preserved here rather than hidden.
