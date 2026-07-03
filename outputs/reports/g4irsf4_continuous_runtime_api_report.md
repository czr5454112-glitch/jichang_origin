# G4IRSF4 Continuous Runtime API Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

## Implemented Surface

| API | Status | Continuity | No Full A* |
| --- | --- | --- | --- |
| g4irsf4_no_astar_streaming_replay_from_jsonl | IMPLEMENTED | single C++ replay window | true |

The API is intentionally a new G4IRSF4 surface. Existing G4I batch replay remains available, but G4IRSF4 continuous runs should use the JSONL streaming entry.
