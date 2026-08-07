# G4IRSF19 Route scorer paired campaign

This campaign holds the existing G18 J2 timing/merge boundary fixed and changes only the native one-hop Route scorer (S1/S2/S3/S4). No new model is trained and no second routing framework is introduced.

| Case | Pair | Trace | Safety B/T | Matched branch | Mutations | Mean TTH delta (s) | P95 delta (s) | Route-wait delta (s) | Events delta |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| prefix_144 | S1/S2 | COMPLETE_CAPTURE_SAME_STATE_MATCH | True/True | 475 | 0 | 0.0000 | 0.0000 | 0.0000 | 0 |
| prefix_144 | S1/S3 | COMPLETE_CAPTURE_SAME_STATE_MATCH | True/True | 475 | 0 | 0.0000 | 0.0000 | 0.0000 | 0 |
| prefix_144 | S1/S4 | COMPLETE_CAPTURE_SAME_STATE_MATCH | True/True | 475 | 0 | 0.0000 | 0.0000 | 0.0000 | 0 |
| scale_1x | S1/S2 | NOT_COLLECTED_CAPACITY_MODE | True/True | 0 | - | 0.0000 | 0.0000 | 0.0000 | 0 |
| scale_1x | S1/S3 | NOT_COLLECTED_CAPACITY_MODE | True/True | 0 | - | 0.0000 | 0.0000 | 0.0000 | 0 |
| scale_1x | S1/S4 | NOT_COLLECTED_CAPACITY_MODE | True/True | 0 | - | -1.0324 | -5.8000 | -1.1002 | -35608 |
| scale_2x | S1/S2 | NOT_COLLECTED_CAPACITY_MODE | True/True | 0 | - | 0.0000 | 0.0000 | 0.0000 | 0 |
| scale_2x | S1/S3 | NOT_COLLECTED_CAPACITY_MODE | True/True | 0 | - | 0.0000 | 0.0000 | 0.0000 | 0 |
| scale_2x | S1/S4 | NOT_COLLECTED_CAPACITY_MODE | True/True | 0 | - | -514.0214 | -3709.4205 | -67.6113 | -1376967 |

## Interpretation boundary

Evidence traces are matched by immutable segment/task identity, current node, goal and the candidate next-node set. A selected-next difference is a directly observed mutation. Unmatched divergent trajectories and any truncation remain explicit, so the mutation count is a lower bound rather than a cloned-state counterfactual claim.

Capacity cases deliberately retain no decision or event rows. They report only paired business, safety and native summary metrics. Route wait is the per-raw-task sum of native junction queue wait; merge-grant wait is a diagnostic subset and must not be added to it.

This fixed-map result is research evidence, not production promotion authorization.
