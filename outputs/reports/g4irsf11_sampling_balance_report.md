# G4IRSF11 Decision-Level Stratified Sampling Balance

Generated: `2026-07-23`.
Schema: `czr005.g4irsf11.decision_trace.v1`.
Candidate order: `next_node_ascending`.
Model score semantics: `lower_is_better_cost` (prediction=min cost; margin=second_min-min).
Reservoir: `order_independent_bounded_sha256_priority_reservoir`.

## Population and sampling

| Metric | Value |
| --- | --- |
| input_decision_count | 26692 |
| eligible_hard_case_count_before_dedupe | 10571 |
| routine_decision_count_excluded | 16121 |
| unique_hard_case_count_after_dedupe | 10571 |
| deterministic_repeat_count_removed | 0 |
| stratum_count | 853 |
| sample_count | 9397 |
| sampling_limit | 50000 |
| minimum_per_stratum | 1 |
| maximum_per_stratum | 64 |
| strata_below_requested_minimum | 0 |
| sampling_seed | czr005-g4irsf11-stratified-reservoir-v1 |
| reservoir_method | order_independent_bounded_sha256_priority_reservoir |
| maximum_retained_candidate_rows | 9397 |

Minimum-quota status: `PASS`. A shortfall is never converted to PASS.
High-flow/fault/tail coverage status: `PASS` (high_flow=True, fault_local_active=True, tail=True).
Fault action coverage requires at least one committed `fault_local_active` decision; observed=14. Scenario metadata alone never satisfies this gate.
Trace shard completeness: `PASS` (stored=26692, seen=28974).

## Hard-case reason coverage before deduplication

| Reason | Count |
| --- | --- |
| downstream_pressure | 3727 |
| fallback_or_shield_selected | 497 |
| local_fault_state | 14 |
| local_queue_pressure | 795 |
| low_model_margin | 158 |
| model_fallback_disagreement | 481 |
| p95_tail | 1001 |
| p99_tail | 266 |
| risk_gate_triggered | 481 |
| rule:pibt_lite_safe_handoff | 481 |
| rule:predicted_candidate_allowed | 16 |
| source_queue_delay | 8680 |
| source_queue_long_backlog | 8680 |

## Largest strata

| Scenario | Scale | Source | Goal | Junction | Fault | Reason | Tail | Total | Unique | Quota | Weight |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| trace_highflow_2p5 | 2.5 | 52 | 49 | 30 | no_fault | source_queue_delay+source_queue_long_backlog | body | 180 | 180 | 64 | 2.8125 |
| trace_fault_delayed | 2.5 | 52 | 49 | 30 | fault_scenario_inactive_here | source_queue_delay+source_queue_long_backlog | body | 180 | 180 | 64 | 2.8125 |
| trace_fault_delayed | 2.5 | 52 | 49 | 31 | fault_scenario_inactive_here | source_queue_delay+source_queue_long_backlog | body | 178 | 178 | 64 | 2.78125 |
| trace_highflow_2p5 | 2.5 | 52 | 49 | 31 | no_fault | source_queue_delay+source_queue_long_backlog | body | 178 | 178 | 64 | 2.78125 |
| trace_highflow_4p0 | 4.0 | 52 | 49 | 30 | no_fault | source_queue_delay+source_queue_long_backlog | body | 165 | 165 | 64 | 2.57812 |
| trace_highflow_4p0 | 4.0 | 52 | 49 | 31 | no_fault | source_queue_delay+source_queue_long_backlog | body | 164 | 164 | 64 | 2.5625 |
| trace_fault_delayed | 2.5 | 52 | 49 | 29 | fault_scenario_inactive_here | source_queue_delay+source_queue_long_backlog | body | 138 | 138 | 64 | 2.15625 |
| trace_highflow_2p5 | 2.5 | 52 | 49 | 29 | no_fault | source_queue_delay+source_queue_long_backlog | body | 138 | 138 | 64 | 2.15625 |
| trace_highflow_4p0 | 4.0 | 52 | 49 | 29 | no_fault | source_queue_delay+source_queue_long_backlog | body | 128 | 128 | 64 | 2 |
| trace_fault_delayed | 2.5 | 52 | 49 | 32 | fault_scenario_inactive_here | source_queue_delay+source_queue_long_backlog | body | 94 | 94 | 64 | 1.46875 |
| trace_highflow_2p5 | 2.5 | 52 | 49 | 32 | no_fault | source_queue_delay+source_queue_long_backlog | body | 94 | 94 | 64 | 1.46875 |
| trace_highflow_2p5 | 2.5 | 52 | 50 | 30 | no_fault | source_queue_delay+source_queue_long_backlog | body | 93 | 93 | 64 | 1.45312 |
| trace_fault_delayed | 2.5 | 52 | 50 | 30 | fault_scenario_inactive_here | source_queue_delay+source_queue_long_backlog | body | 93 | 93 | 64 | 1.45312 |
| trace_fault_delayed | 2.5 | 52 | 50 | 31 | fault_scenario_inactive_here | source_queue_delay+source_queue_long_backlog | body | 88 | 88 | 64 | 1.375 |
| trace_highflow_2p5 | 2.5 | 52 | 50 | 31 | no_fault | source_queue_delay+source_queue_long_backlog | body | 88 | 88 | 64 | 1.375 |
| trace_highflow_4p0 | 4.0 | 52 | 50 | 31 | no_fault | source_queue_delay+source_queue_long_backlog | body | 87 | 87 | 64 | 1.35938 |
| trace_highflow_4p0 | 4.0 | 52 | 50 | 30 | no_fault | source_queue_delay+source_queue_long_backlog | body | 87 | 87 | 64 | 1.35938 |
| trace_highflow_2p5 | 2.5 | 52 | 49 | 52 | no_fault | source_queue_delay+source_queue_long_backlog | body | 81 | 81 | 64 | 1.26562 |
| trace_fault_delayed | 2.5 | 52 | 49 | 52 | fault_scenario_inactive_here | source_queue_delay+source_queue_long_backlog | body | 81 | 81 | 64 | 1.26562 |
| trace_highflow_4p0 | 4.0 | 52 | 49 | 32 | no_fault | source_queue_delay+source_queue_long_backlog | body | 76 | 76 | 64 | 1.1875 |

The hard-case CSV is a balanced decision index, not a first-50k prefix. `sample_weight` is the unique stratum population divided by its effective quota. Exact pre-deduplication counts are retained separately.

Original arrival, Java arrival epoch, Java source release, and queue delay are linked to every decision in the source-release mapping table; backlog is not represented only by a scenario-level matrix.
