# G4IRSF16 Stage 16A model-ready data report

## Outcome

The formal G4IRSF15 release was projected into separated I3, I4, and H_system Parquet datasets. No model was trained. The final-audit partition is sealed and its row-level outcomes were not used for rule, threshold, or model selection.

## Join and leakage contract

- Labels join the target-address frame only by `descriptor_id` (one-to-one).
- Compact causal evidence joins by `target_key`, with the entry pair hash required to equal the formal label pair hash.
- H_system other-bag tails use only `externality_runtime_bag_ids`; harm is `max(0, treatment completion - baseline completion)`.
- H_bag has no observed system externality. Its externality and risk-adjusted utility fields remain Arrow null, not zero.
- Airport-wide target-address `queued/merge/fault` counters are forbidden and are not local feature proxies.
- Missing exact F2 queue/calendar/history/score features remain Arrow null unless a matched runtime feature cache is supplied.

## Label inventory

| Kind | Rows | Beneficial | Neutral | Harmful |
| --- | --- | --- | --- | --- |
| I3 | 1086 | 23 | 30 | 1033 |
| I4 | 1086 | 24 | 325 | 737 |

## Four-way support

| Kind | Split | Rows | Beneficial | Neutral | Harmful |
| --- | --- | --- | --- | --- | --- |
| I3 | train | 654 | 13 | 18 | 623 |
| I3 | calibration | 165 | 3 | 5 | 157 |
| I3 | validation | 150 | 3 | 4 | 143 |
| I3 | final_audit | 117 | 4 | 3 | 110 |
| I4 | train | 678 | 14 | 207 | 457 |
| I4 | calibration | 153 | 3 | 46 | 104 |
| I4 | validation | 164 | 3 | 50 | 111 |
| I4 | final_audit | 91 | 4 | 22 | 65 |

The pure component hash produced {'train': 1332, 'calibration': 318, 'validation': 314, 'final_audit': 208}. Source/time/node/kind are balance diagnostics, not union edges, because coarse unioning collapses the formal panel into giant components.

## Feature availability

Matched live runtime feature rows: 2172/2172. Rows complete across all 10 dynamic deployment columns: 2172/2172. `downstream_pressure` was removed because no exact local runtime scalar is exposed; physical-fault state remains owned by the supervisor shield. No shield/risk proxy was substituted.

| Deployment feature | Null rows | Origin |
| --- | --- | --- |
| deadline_slack_seconds | 0 | static |
| wait_age_seconds | 0 | static |
| current_queue_length | 0 | dynamic |
| target_queue_length | 0 | dynamic |
| target_scheduled_incoming | 0 | dynamic |
| current_next_available_wait_seconds | 0 | dynamic |
| target_next_available_wait_seconds | 0 | dynamic |
| alternative_action_count | 0 | static |
| total_legal_action_count | 0 | static |
| current_node_out_degree | 0 | static |
| current_node_type | 0 | static |
| current_node_service_seconds | 0 | static |
| baseline_edge_travel_seconds | 0 | static |
| intervention_edge_travel_seconds | 0 | static |
| static_remaining_current_seconds | 0 | static |
| static_remaining_baseline_seconds | 0 | static |
| static_remaining_intervention_seconds | 0 | static |
| static_potential_delta_seconds | 0 | static |
| f2_model_margin | 0 | dynamic |
| f2_raw_score | 0 | dynamic |
| recent_visit_count | 0 | dynamic |
| short_history_repeat_count | 0 | dynamic |
| storage_in_leg | 0 | static |
| storage_out_leg | 0 | static |
| direct_leg | 0 | static |
| event_hour_sin | 0 | static |
| event_hour_cos | 0 | static |
| baseline_release | 0 | static |
| advertised_fault | 0 | dynamic |

`pre_action_retry_count` and `pre_action_decision_count` are retained only in the audit partition because the frozen deployment schema does not include them.

## Subgroup coverage (audit identities only)

| Kind | Nodes | Sources | Goals | Hours | Task classes |
| --- | --- | --- | --- | --- | --- |
| I3 | 15 | 8 | 4 | 21 | direct, storage_in, storage_out |
| I4 | 40 | 8 | 4 | 20 | direct, storage_in, storage_out |

## Sparse H_system externality (selectable partitions only)

Selectable H_system rows: 232; nonempty external sets: 131; maximum external affected count: 365; maximum positive other-bag harm: 78.100100 s; maximum CVaR95: 54.036885 s. P95 uses linear type-7 interpolation and CVaR95 uses the largest `ceil(0.05*n)` clipped harms.
Final-audit H_system outcomes are excluded from every tail statistic above.

Risk-balanced utility is fixed before training as direct benefit minus the penalties {'positive_mean_harm': 1.0, 'cvar95_harm': 0.5, 'log_external_affected_count': 1.0, 'extra_deadline_miss': 300.0}. It is null for H_bag rows.

## Learnability boundary exposed by Stage 16A

- `I3_REROUTE_MODEL_NOT_AUTHORIZED`: train contains only 13 beneficial I3 rows and all selectable partitions contain 19, already below the preregistered train minimum of 24. This conclusion does not require opening final audit.
- I4 support screen: the published full-panel census is beneficial=24, harmful=737; selectable positives={'train': 14, 'calibration': 3, 'validation': 3} (total=20). Because final-audit labels cannot authorize training, the selectable total remains below 24: `NOT_AUTHORIZED`.
- H_system extra-deadline-miss labels are degenerate at zero in the formal panel; a deadline-miss classifier is not trainable from this release.

## Final-audit seal

`final_audit` contains 208 rows. The builder records the predeclared descriptive support census, but authorization ignores final-audit labels and writes `SEALED_NOT_CONSUMED`; it performs no fitting, threshold search, ranking, or candidate selection.
