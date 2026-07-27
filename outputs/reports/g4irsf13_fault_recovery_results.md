# G4IRSF13 Fault Recovery Results

Status: `FAULT_DISCRIMINATING_PASS`

Executed cases: 13; informative: 12; hard failures: 0.

## Matched local A/B

| Case | Policy | P | Complete | TTH s | Exposure | Unsafe | Delta vs comparator s | Causal status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G0_no_fault | True | P2 | True | 45.402000 | 0 | 0 |  | NOT_APPLICABLE |
| G1_physical_shield_only | False | P2 | True | 141.402000 | 769 | 0 |  | NOT_APPLICABLE |
| G2_control_physical_shield_only_p0 | False | P0 | True | 141.402000 | 769 | 0 |  | NOT_APPLICABLE |
| G2_ddi_local_policy | True | P0 | True | 49.602000 | 3 | 0 | -91.800000 | MATCHED_PHYSICAL_SHIELD_POLICY_CONTRIBUTION_PASS |
| G3_ddi_plus_p2 | True | P2 | True | 49.602000 | 3 | 0 | -91.800000 | MATCHED_PHYSICAL_SHIELD_POLICY_CONTRIBUTION_PASS |
| G4_v3_fault_aware_plus_p2 |  |  |  |  | 0 |  |  | NOT_APPLICABLE |
| G5_delayed_message | True | P2 | True | 49.602000 | 3 | 0 | +0.000000 | UNMATCHED_FAULT_OR_CONTROL_CONFIGURATION |
| G6_dropped_message | True | P2 | True | 49.602000 | 3 | 0 | -91.800000 | UNMATCHED_FAULT_OR_CONTROL_CONFIGURATION |
| G7_repair_reopen | True | P2 | True | 49.602000 | 3 | 0 | -6.800000 | MATCHED_PHYSICAL_SHIELD_POLICY_CONTRIBUTION_PASS |
| G7_control_physical_shield_only | False | P2 | True | 56.402000 | 89 | 0 |  | NOT_APPLICABLE |
| G8_multi_fault | True | P2 | True | 69.402000 | 289 | 0 | +0.000000 | NO_POSITIVE_POLICY_CONTRIBUTION_DEMONSTRATED |
| G8_control_physical_shield_only | False | P2 | True | 69.402000 | 289 | 0 |  | NOT_APPLICABLE |
| G9_cut_isolation | True | P2 | True | 70.652000 | 0 | 0 | +0.000000 | NO_LOCAL_POLICY_ACTION_OBSERVED_PHYSICAL_FALLBACK_ONLY |
| G9_control_physical_shield_only | False | P2 | True | 70.652000 | 0 | 0 |  | NOT_APPLICABLE |

Causal promotion is granted only when policy-on and policy-off share the same always-on physical shield, the case has actual exposure, policy-on improves completion/delay/recovery/backlog, and unsafe edge entry remains zero. Dropped DDI messages intentionally fall back to the physical interlock.

## Safety, generation, and containment audit

Frozen binary `814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7` matched every executed row: `True`.

Every injected edge recorded an ordered physical `FAULT -> REPAIR` generation transition, every completed repair re-entry boost was cleared, and aggregate unsafe entry remained `0`.

G9 faults the real 0->6 edge at release and observes first-edge credit issue rejection by the non-bypassable physical interlock in both matched policy-on/off runs. Successful credits are issued, bound, and consumed atomically by this event runtime, so these rows do not claim a live-credit revocation. Formal one-bag probes also had no uncommitted P2 batch at the fault instant; prepare/commit generation rollback is therefore retained as real-map unit evidence rather than reported as a positive runtime cancellation.

The G4 v3 fault-aware row is `NOT_RUN`: fresh untouched holdout failed the offline learning gate, so runtime activation and closed-loop fault evaluation are forbidden.
