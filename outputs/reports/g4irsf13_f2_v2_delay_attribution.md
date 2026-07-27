# G4IRSF13 F2-v2 Delay Attribution

Status: `TIMING_ACCOUNTING_PASS_CAUSAL_ATTRIBUTION_PARTIAL`

## Reproduced matched-denominator result

- F2: 41.514218717973 min
- frozen v2-safe: 41.495306987809 min
- paired mean gap: +1.134703810 s/bag
- mechanical timing reconstruction: 100.000000%
- bounded responsibility coverage: 100.000000%
- unresolved responsibility (`other`): -0.000000000 s/bag

## Paired delta distribution

| Mean | Median | p90 | p95 | p99 | Max |
| --- | --- | --- | --- | --- | --- |
| +1.134704 | +0.289000 | +8.535944 | +23.934399 | +78.561696 | +246.777652 |

F2 faster/slower/exact ties: 11760/16746/0 (tie tolerance 1.0e-09s).

## Mechanical timing ledger

| Component | F2 s/bag | v2 s/bag | Delta s/bag | Role |
| --- | --- | --- | --- | --- |
| release_interface_alignment | 0.000000 | 34.062696 | -34.062696 | MEASURED_ADDITIVE |
| source_queue_wait | 21.763094 | 0.000000 | +21.763094 | MEASURED_ADDITIVE |
| junction_queue_wait | 17.790837 | 0.000000 | +17.790837 | MEASURED_ADDITIVE |
| resource_calendar_wait | 0.000000 | 3.645873 | -3.645873 | MEASURED_ADDITIVE |
| goal_completion_time | 248.593031 | 247.458327 | +1.134704 | DIAGNOSTIC_NON_ADDITIVE |
| detour_extra_time | 0.013387 | 0.707037 | -0.693650 | DIAGNOSTIC_NON_ADDITIVE |
| edge_travel_time | 198.609921 | 199.303571 | -0.693650 | MEASURED_ADDITIVE |
| node_service_time | 10.429180 | 10.446187 | -0.017007 | MEASURED_ADDITIVE |
| timing_unresolved_residual |  |  | +0.000000 | RESOLVED_WITHIN_TOLERANCE |
| scheduled_ebs_dwell | 2242.260092 | 2242.260092 | +0.000000 | MEASURED_ADDITIVE |
| pibt_prepare_wait | 0.000000 | 0.000000 | +0.000000 | MEASURED_ADDITIVE |
| pibt_rollback_wait | 0.000000 | 0.000000 | +0.000000 | MEASURED_ADDITIVE |
| fault_hold | 0.000000 | 0.000000 | +0.000000 | MEASURED_ADDITIVE |
| loop_extra_time | 0.000000 | 0.000000 | +0.000000 | DIAGNOSTIC_NON_ADDITIVE |

The additive ledger is mutually exclusive. `detour_extra_time` and `loop_extra_time` are diagnostic subsets of executed travel, while `goal_completion_time` is an outcome total; they are never added a second time. F2 R3 calendar/dispatch holds are owned by the measured junction-queue interval. P2 prepare/rollback is instantaneous in the current runtime, so event counters are not mislabeled as wait time. For v2, resource-calendar wait is reconstructed from finish time minus source wait and physical travel/service. Its legacy `wait_seconds` aggregate is a cross-check because the old closed-boundary code advances by `1e-6s` but records only waits strictly larger than that threshold; the maximum observed discrepancy is 2.00000068e-06s.

## Bounded responsibility ledger

| Responsibility | Delta s/bag | Evidence status |
| --- | --- | --- |
| source_service_ordering | -12.318139 | OBSERVED_ASSOCIATIVE_HYPOTHESIS |
| merge_ordering | +14.144963 | OBSERVED_ASSOCIATIVE_HYPOTHESIS |
| route_choice | -0.693650 | MEASURED_EXECUTED_PATH_TIMING_ATTRIBUTION |
| p2_arbitration | +0.000000 | MEASURED_EXPLICIT_ZERO_UNMATCHED_QUEUE_EFFECT |
| goal_handling | +0.001530 | MEASURED_SERVICE_SEMANTIC_ATTRIBUTION |
| storage_leg_ordering | +0.000000 | MEASURED_COMMON_DENOMINATOR_ATTRIBUTION |
| other | -0.000000 | UNRESOLVED_CAUSAL_RESPONSIBILITY |

These responsibility rows are mutually exclusive and add to the observed mean gap, but additivity is not causal identification. Source/service, merge, route, goal, and storage rows are bounded localization hypotheses; P2 effects still need a matched intervention. Anything not defensibly assigned remains explicit in `other`.
Causal attribution status: `PARTIAL_NO_MATCHED_INTERVENTION`. No matched runtime-state clone/counterfactual intervention was executed in this diagnostic.

## Divergence and hotspot evidence

1841 segments have an observed first action divergence. The committed sample contains 256 rows.

| Slice | Value | Bags | Average contribution s/all bags |
| --- | --- | --- | --- |
| goal | 50 | 8899 | +1.372543 |
| first_divergence_node | NO_DIVERGENCE | 26667 | +1.253167 |
| top_1pct_delta | True | 286 | +1.235566 |
| merge_involvement | True | 28506 | +1.134704 |
| pibt_involvement | False | 28475 | +1.080047 |
| entry_time_band | early | 9502 | +1.055265 |
| top_1pct_f2_slow | False | 28220 | +0.993193 |
| hour | 6 | 3107 | +0.977841 |
| deadline_slack_bucket | tight | 15840 | +0.944792 |
| bag_class | storage_in_out | 15097 | +0.927172 |
| source | 2 | 3199 | +0.786948 |
| source | 1 | 3193 | +0.712476 |

At each divergence only the current v2-safe next action is retained under `offline_labels`. The runtime feature object is rebuilt from an explicit local-state/candidate allowlist and contains no teacher path, future schedule, post-hoc outcome, or label source.

## Validation

| Gate | Status | Actual | Expected |
| --- | --- | --- | --- |
| segment_alignment | PASS | 43603 | 43603 |
| raw_bag_alignment | PASS | 28506 | 28506 |
| storage_dwell_counted_once | PASS | 2242.260092059321 | 2242.260092059321 |
| f2_segment_component_reconstruction | PASS | 3.6777692002942786e-11 | <=1e-6 seconds |
| v2_segment_component_reconstruction | PASS | 1.0174971976084635e-11 | <=1e-6 seconds |
| v2_reported_wait_epsilon_crosscheck | PASS | 2.0000006770715117e-06 | <=1.1e-6 * (path node count + 1) per segment |
| no_fault_stage_b_scope | PASS | 0 | 0 |
| complete_f2_decision_trace | PASS | 340810 | non-empty and not truncated |
| teacher_future_feature_leakage | PASS | 0 | 0 |
| f2_matched_raw_entry_mean | PASS | 41.514218717973435 | 41.514218717973414 |
| v2_matched_raw_entry_mean | PASS | 41.49530698780894 | 41.49530698780892 |
| f2_minus_v2_gap | PASS | 1.134703809869734 | 1.1347038098698192 |
| timing_reconstruction_coverage | PASS | 0.9999999999995491 | >=0.90 |
| bounded_responsibility_localization_coverage | PASS | 0.9999999999999744 | diagnostic target >=0.90 or explicit unresolved |
| f2_archive_integrity | PASS | 3fde48fe4d9974f43dde7971f3a0b9926f8f91090693b0e71584dddf8a496e0b | descriptor/hash validation completed |
| v2_safe_archive_integrity | PASS | 93e665c653639adaff221d27b9589afc05736e1112cf238b0fa43beeedaf9c1a | descriptor/hash validation completed |

No hard validation failures.

The fifth CSV, `g4irsf13_delay_attribution_validation.csv`, is an auditable supplement to the four Stage-B science tables. Every gate is rendered from an observed check; no PASS value is hard-coded.

## Claim boundary

Diagnostic replay attribution only; sealed G4IRSF12 evidence remains immutable. Detour/loop are subsets and goal completion is an outcome, so none is double-counted. The timing ledger is an accounting identity; the separate responsibility ledger is bounded localization and not causal promotion evidence. No matched state-clone intervention was run, so causal attribution remains explicitly partial even when localization coverage is above its diagnostic target.
