# G4IR2 Learning Policy Next Iteration

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `5d4be59`
Upstream: `origin/codex/czr005-rewrite`
Upstream HEAD: `5d4be59`

## Feature Cost Benefit

| Component | Stage | Mean Seconds | Recommendation |
| --- | --- | --- | --- |
| mlp_policy_score | model_inference | 0.04520038 | keep; rule-only collapses planned count on G4D scope |
| pibt_lite_fallback | pibt_lite_fallback_scoring | 0.02726482 | keep as safety fallback; optimize only if profile dominates |
| historical_risk_gate | historical_risk_lookup | 0.0044605 | retain unless next training shows no effect under shift |
| bottleneck_risk_gate | bottleneck_score_computation | 0.00469446 | retain as interpretable local pressure feature |
| trace_payload | trace_row_construction | 0.0201963 | disable in promoted runtime unless debugging |

G4IR2 does not train a new model. It identifies which tiny-policy and risk-gate variants should be trained or calibrated next after the runtime bottleneck is closed.
