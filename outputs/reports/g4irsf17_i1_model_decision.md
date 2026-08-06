# G4IRSF17 I1 Phase-D model decision

- Status: `TRAINED_NOT_AUTHORIZED`
- Offline candidate authorized: `false`
- Runtime closed-loop authorized: `false` (requires later native shadow/system evidence)
- Final audit consumed: `false`
- Model features contain task/source IDs: `false`

## Input and split support

Valid matched feature/effect rows: 256 of 520.

Rejected-row reasons: {"CAUSAL_EFFECT_NOT_ELIGIBLE": 264}

| split | rows | beneficial | harmful | neutral |
| --- | ---: | ---: | ---: | ---: |
| train | 159 | 10 | 10 | 139 |
| calibration | 40 | 3 | 2 | 35 |
| validation | 34 | 2 | 2 | 30 |
| final_audit | 23 | sealed | sealed | sealed |

Support pass: `false`.
H_bag `BOUNDED_DIRECT_SWAP_COHORT` development rows: 225.
H_system externality evidence rows: 8.
H_bag labels are limited to the two direct affected bags plus the fixed deadline penalty; they can train the local ranker but cannot provide full-system or runtime closed-loop authorization.

## Calibration, OOD, and validation

Calibration-fit ECE: benefit=0.014767, harm=0.000652.
Validation ECE: benefit=0.061493, harm=0.007753.

| family | rows | top-1 | mean advantage vs current | harmful override rate |
| --- | ---: | ---: | ---: | ---: |
| FIFO | 34 | 0.941176 | 0.000000 | 0.000000 |
| CURRENT_AGING_Q0 | 34 | 0.941176 | 0.000000 | 0.000000 |
| LOCALIZED_THESIS_RULE | 34 | 0.941176 | 0.000000 | 0.000000 |
| PAIRWISE_LINEAR | 34 | 0.941176 | 0.000000 | 0.000000 |
| TINY_MLP | 34 | 0.941176 | 0.000000 | 0.000000 |
| SELECTIVE_GATE | 34 | 0.941176 | 0.000000 | 0.000000 |

Selective validation: coverage=0.000000, beneficial precision=0.000000, beneficial recall=0.000000, harm veto recall=1.000000, activated utility=0.000000s, OOD rows=6, OOD activations=0.

Source/time diagnostics are task-validation slices; no final-audit row is included. They report any source/time entity overlap with task-train instead of claiming a separately refitted strict holdout.
Bucket diagnostics: leg, queue, slack, source, time, utility_scope

## Promotion checks

- `support`: `fail`
- `task_group_hard_split`: `pass`
- `calibration`: `pass`
- `validation_activation_support`: `fail`
- `beneficial_precision`: `fail`
- `harmful_recall`: `pass`
- `harmful_activation_rate`: `pass`
- `activated_utility`: `fail`
- `ood_abstention`: `pass`
- `learned_not_worse_than_localized_rule`: `pass`
- `h_system_externality_evidence`: `pass`
- `final_audit_sealed`: `pass`

## No-go reasons

- `PROMOTION_SUPPORT_FAILED`
- `PROMOTION_VALIDATION_ACTIVATION_SUPPORT_FAILED`
- `PROMOTION_BENEFICIAL_PRECISION_FAILED`
- `PROMOTION_ACTIVATED_UTILITY_FAILED`

## Evidence boundaries

Training uses only the task-group train partition. Platt calibration and the utility residual bound use only calibration. Promotion metrics use only task-group validation. Source/time and bucket results are diagnostics, not extra promotion samples. The final audit stays sealed.
