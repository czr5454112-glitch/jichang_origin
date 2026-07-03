# G4IRSF3 High-Flow Runtime Optimization Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Measured Chunk Runtime

Measured chunk tasks: `348824`
Measured no-A* seconds: `1022.242`
Approx tasks/second: `341.234`

The immediate blocker is not only speed; it is also that reservation/traffic memory cannot yet be carried across chunks through the runtime API.
