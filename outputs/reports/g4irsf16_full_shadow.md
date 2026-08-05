# G4IRSF16 full 1x shadow report

Status: `PASS_FROZEN_F2_FULL_SHADOW`.

Models proposed actions while the native runtime executed frozen F2 only. This is shadow evidence, not a closed-loop outcome or benefit claim.

## Native F2 hard gates

| Gate | Value |
|---|---:|
| completed segments | 43603 / 43603 |
| raw bags | 28506 |
| failed | 0 |
| conflicts | 0 |
| unsafe edge entries | 0 |
| full A* calls | 0 |
| global scans | 0 |
| future-route reads | 0 |
| unresolved deadlocks | 0 |
| F2 action mutations caused by shadow | 0 |
| illegal proposals | 0 |
| model feature leakage | 0 |

## Shadow coverage

| Kind | Opportunities | Model eligible | Proposals | Coverage | OOD |
|---|---:|---:|---:|---:|---:|
| I4 | 520338 | 520338 | 0 | 0.0 | 4149 |
| I3 | 119407 | 0 | 0 | None | 0 |

I3 status: `I3_REROUTE_MODEL_NOT_AUTHORIZED`. Diagnostic risk-veto artifacts are never converted into rare-route override proposals.

## Offline authorization

- Overall: `CAUSAL_LEARNING_MODEL_NO_GO`
- I4: `I4_SELECTIVE_MODEL_NO_GO`
- I3: `I3_REROUTE_MODEL_NOT_AUTHORIZED`
- Final audit: `SEALED_NOT_CONSUMED`

## Promotion boundary

I4 preregistered coverage range check: `False`.
Beneficial-support overlap is intentionally not computed from runtime shadow rows, because causal outcome labels are forbidden model/runtime inputs; it remains an offline audit join before closed-loop promotion.

## Artifacts

- Per-decision predictions: `outputs/tables/g4irsf16_shadow_predictions.jsonl.zst`
- Activation groups: `outputs/tables/g4irsf16_shadow_activation_by_group.csv`
- Native trace evidence: `outputs/runtime/g4irsf16/g4irsf16_f2_off_e4_m0_43603_shards4.metadata.json`
