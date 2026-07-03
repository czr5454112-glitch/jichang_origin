# G4IRSF3 A* Hardness V2 Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Result

| Chunks | Any Hardness Pass? | Negative Preserved |
| --- | --- | --- |
| 11 | False | True |

G4IRSF3 still does not prove A* is hard on this map and task stream. The static A* lower-bound remains much faster, and the full Java/CIE baseline remains blocked or unavailable in this local audit.
