# G4IRSF25 contextual corridor learning

Status: OFFLINE_EVIDENCE_COMPLETE; native policy selection is intentionally outside this report.

## Evidence inputs

- Paired dataset: `artifacts/datasets/g4irsf25_short_horizon_pairs_compact.jsonl`
- G24 corridor source: `outputs/tables/g4irsf24_decision_summary.json#reconvergent_corridor.corridors`
- Paths are trace metadata only and are not runtime model features.

## Action and opportunity ceilings

- Full-state useful opportunities: `544` / `1024`
- Full-state mean possible improvement fraction: `0.562093`
- Opportunity mass: `2323446.867805`
- Stable reversal branches: `9`
- Local-observation ranking ceiling: `0.900391`
- S4 action accuracy in the same paired rows: `0.468750`
- Local ceiling mean regret: `73.771719` seconds

## L1 two-head ridge

| split | system MAE (s) | ranking | beneficial precision | harmful mutation rate | regret (s) | mutations | safety failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| validation | 1535.715026 | 0.873171 | 0.870968 | 0.129032 | 249.659188 | 124 | 0 |
| test | 1549.795466 | 0.829268 | 0.843137 | 0.156863 | 292.681258 | 102 | 0 |

## Optional evidence gates

### L2

- Status: `TRIGGERED`
- Evidence reasons: `full_state_mean_gain_at_least_1pct, at_least_100_useful_opportunities, local_ceiling_above_s4_ordering, l1_has_direction_but_remaining_regret`
- Artifact emitted: `true`

| split | system MAE (s) | ranking | beneficial precision | harmful mutation rate | regret (s) | mutations | safety failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| validation | 2150.088536 | 0.629268 | 0.682927 | 0.317073 | 743.859966 | 123 | 0 |
| test | 1788.409336 | 0.546341 | 0.578947 | 0.421053 | 591.042438 | 114 | 0 |

### L3

- Status: `NOT_TRIGGERED`
- Evidence reasons: `none`
- Artifact emitted: `false`
- Residual/feedback correlation: `0.000000`
- Adaptive online benefit is `NOT_MEASURED` here; it requires native closed-loop evidence and is not fabricated from static pairs.
