# G4IRSF4 Java/CIE Baseline Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

| Attempt | Status | Notes |
| --- | --- | --- |
| dependency_inventory | PASS | Netty jars are present under legacy Java_jar. |
| compile_original_java_with_discovered_jars | PASS | Output directory is temporary; legacy tree is not modified. |
| run_original_java_headless_RUN_Main | BLOCKED | A nonzero result keeps Java/CIE runtime baseline blocked. |

If headless Java remains blocked, G4IRSF4 uses the stronger Java-semantics proxy boundary and keeps the original Java/CIE baseline as unavailable.
