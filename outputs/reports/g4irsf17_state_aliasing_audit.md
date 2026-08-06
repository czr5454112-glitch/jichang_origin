# G4IRSF17 state aliasing audit

Status: **`CANONICAL_ABLATION_COMPLETE_LEGACY_29_UNAVAILABLE`**

Input effect rows: **520**; eligible native causal feature rows: **248**.

Causal scope: **`H_bag`**. H_system rows use a different externality utility and are not mixed into the H_bag nearest-neighbor labels.

Comparison scope: **`CANONICAL_STATIC_LOCAL_VS_FULL_39_ABLATION`**. Exact legacy-29 snapshot available: **False**.

When the exact G16 29D vector is absent at the I1 source-order boundary, the report does not synthesize a proxy or claim legacy-vs-39D superiority. It instead records a real native 39D static-local versus full temporal/pressure/merge ablation; model authorization remains governed by causal support and externality gates.

The campaign passed I1 effect rows to `czr005.g4irsf17.run_state_aliasing_audit` when that package hook was available, using `system_utility` as the outcome.  Feature ablation was called through the package's canonical implementation as well; the campaign runner does not duplicate model semantics.

```json
{
  "augmented": {
    "conditional_variance": 0.1411111111111111,
    "coverage": 0.907258064516129,
    "distance_threshold": 0.35,
    "feature_count": 39,
    "mean_neighbor_distance": 0.1494217908938054,
    "pair_count": 225,
    "row_count": 248,
    "sign_disagreement_rate": 0.0
  },
  "feature_names": {
    "augmented": [
      "candidate_local_rank",
      "candidate_deadline_slack_seconds",
      "candidate_wait_age_seconds",
      "candidate_leg_priority",
      "candidate_repair_priority",
      "deadline_slack_delta_to_baseline_seconds",
      "wait_age_delta_to_baseline_seconds",
      "leg_priority_delta_to_baseline",
      "urgency_delta_to_granted_seconds",
      "wait_delta_to_granted_seconds",
      "source_queue_length",
      "source_queue_capacity",
      "source_queue_utilization",
      "source_queue_generation_delta",
      "release_count_10s",
      "release_count_30s",
      "release_count_60s",
      "admission_count_10s",
      "admission_count_30s",
      "admission_count_60s",
      "queue_slope_10s",
      "queue_slope_30s",
      "queue_slope_60s",
      "first_edge_credit_slack_seconds",
      "target_queue_length",
      "target_queue_capacity",
      "target_queue_utilization",
      "target_scheduled_incoming",
      "estimated_service_rate_60s",
      "drain_slope_60s",
      "service_weighted_pressure",
      "one_hop_ttl_pressure",
      "two_hop_ttl_pressure",
      "merge_pending_count",
      "merge_oldest_request_age_seconds",
      "merge_token_generation_delta",
      "time_to_next_service_opportunity_seconds",
      "recent_incoming_grants_60s",
      "incoming_grant_imbalance_60s"
    ],
    "legacy": [
      "candidate_local_rank",
      "candidate_deadline_slack_seconds",
      "candidate_wait_age_seconds",
      "candidate_leg_priority",
      "candidate_repair_priority",
      "deadline_slack_delta_to_baseline_seconds",
      "wait_age_delta_to_baseline_seconds",
      "leg_priority_delta_to_baseline",
      "urgency_delta_to_granted_seconds",
      "wait_delta_to_granted_seconds",
      "source_queue_length",
      "source_queue_capacity",
      "source_queue_utilization",
      "first_edge_credit_slack_seconds",
      "target_queue_length",
      "target_queue_capacity",
      "target_queue_utilization",
      "target_scheduled_incoming"
    ]
  },
  "improvement": {
    "conditional_variance_reduction": 0.053502710027100275,
    "coverage_delta": -0.08467741935483875,
    "sign_disagreement_reduction": 0.008130081300813009
  },
  "legacy": {
    "conditional_variance": 0.19461382113821138,
    "coverage": 0.9919354838709677,
    "distance_threshold": 0.35,
    "feature_count": 18,
    "mean_neighbor_distance": 0.050497037565843415,
    "pair_count": 246,
    "row_count": 248,
    "sign_disagreement_rate": 0.008130081300813009
  },
  "outcome": "system_utility",
  "schema": "czr005.g4irsf17.state_aliasing_audit.v1"
}
```
