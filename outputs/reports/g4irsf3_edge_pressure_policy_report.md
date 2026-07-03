# G4IRSF3 Edge Pressure Policy Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Boundary

Edge overlap remains diagnostic only. G4IRSF3 does not turn it into edge_capacity=1 and does not count it as a primary safety conflict.

| Variant | Runtime Status | Promoted? |
| --- | --- | --- |
| edge_diag_only | G4IRSF2_DIAGNOSTIC_SHADOW_REUSED | False |
| soft_edge_pressure_low | G4IRSF2_DIAGNOSTIC_SHADOW_REUSED | False |
| soft_edge_pressure_mid | G4IRSF2_DIAGNOSTIC_SHADOW_REUSED | False |
| soft_edge_pressure_high | G4IRSF2_DIAGNOSTIC_SHADOW_REUSED | False |
| edge_headway_shadow_audit | G4IRSF2_DIAGNOSTIC_SHADOW_REUSED | False |
| fault_aware_dead_end_pressure_depth3_shadow | SHADOW_LOCAL_POLICY_PROXY_NOT_PROMOTED | False |
