# G4IRSF4 A* Baseline Boundary Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `284475d`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false
legacy_java_modified: false

| Baseline | Status | Lower Bound Only? | Notes |
| --- | --- | --- | --- |
| static_astar_lower_bound_proxy | available | True | Fast lower bound only. |
| java_semantics_proxy_b_light | improved_proxy | False | Closer to Java than static A*, still not original runtime. |
| original_java_cie_runtime | blocked | False | Use only if compile/headless run succeeds. |

Static A* remains a lower-bound proxy. It is not a full Java/CIE scheduler baseline.
