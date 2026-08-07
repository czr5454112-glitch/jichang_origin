# G4IRSF18 merge-local learning campaign

Decision: **`TEACHER_DISTILLATION_GENERALIZES_BUT_COUNTERFACTUAL_CONFLICTS`**.

The dataset contains only real multi-candidate native J2 service opportunities. J2 chosen actions are teacher metadata, never inference inputs. The second target is a reconstructible bounded-local rollout over the pending candidates already visible at that boundary. It is **not** a full-system clone, does not simulate future arrivals, and does not use realized completion outcomes.

## Evidence boundary

- Retained opportunities: 138
- Split counts: {'train': 84, 'validation': 27, 'audit': 27}
- Exclusions: {'singleton': 7829, 'over_bounded_horizon': 0, 'identity_only_local_state': 0, 'duplicate_state_across_traces': 13, 'non_teacher_timing_mode': 0}
- Request/node identities and winner flags are metadata only; none are model features.
- A mutation counts only when the selected candidate's local feature vector differs from FIFO's. Swapping two identity-only duplicates does not count.

## Offline candidate comparison

`top-1` and regret below refer to the bounded-local rollout objective, not teacher agreement.

| Variant | Validation top-1 | Validation regret | Validation utility | Validation mutations | Audit top-1 | Audit regret | Audit utility | Audit mutations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| J3_LINEAR_RESIDUAL | 0.962963 | 0.000025 | -1.697646 | 1 | 0.962963 | 0.000025 | -1.715290 | 1 |
| J4_MLP_RESIDUAL | 1.000000 | 0.000000 | -1.697622 | 0 | 1.000000 | 0.000000 | -1.715265 | 0 |
| J5_STANDALONE | 1.000000 | 0.000000 | -1.697622 | 0 | 0.962963 | 0.000025 | -1.715290 | 1 |
| J6_SET_SCORER | 0.888889 | 0.000134 | -1.697755 | 3 | 0.851852 | 0.000227 | -1.715492 | 4 |
| J7_TEACHER_CF_AFFINE | 0.074074 | 0.019578 | -1.717199 | 25 | 0.074074 | 0.016677 | -1.731942 | 25 |

## Teacher warm start and counterfactual correction

Within observed support, native J2 is exactly `argmax(wait_age_seconds - deadline_slack_seconds)`. Maximum observed wait age is 85.329410s, below the 120s authoritative starvation band.

The validation-selected counterfactual blend is `120.0` with a required non-homomorphic teacher-mutation recall of at least `0.95`.

| Split | Teacher action agreement | Teacher mutation recall | Teacher mutation precision | Predicted mutations | Rollout mean gain vs FIFO | Benefit | Harm | Neutral |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| train | 0.976190 | 0.975610 | 1.000000 | 80 | -0.021086364 | 0 | 80 | 4 |
| validation | 0.962963 | 0.961538 | 1.000000 | 25 | -0.019577772 | 0 | 25 | 2 |
| audit | 0.962963 | 0.961538 | 1.000000 | 25 | -0.016676952 | 0 | 25 | 2 |

The audit therefore separates two facts: the local teacher seam is reproducible/generalizable, while its actions conflict with this rollout objective. This is evidence for a controlled native research test, not evidence of utility improvement or production readiness.

## Native J2 versus native JIT FIFO

These end-to-end results are report-only outcomes and never enter model features or targets.

| Job | Mutations | Paired improve/harm/same | Mean TTH delta | P95 delta | P99 delta | Merge-wait mean delta | Event delta | Safety |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| j2_f2_jit_fair_aging_deadline__s2048 | 134 | 122/48/877 | 0.000000000 | 0.163770000 | 6.005677400 | 0.127487956 | -169 | True |
| j2_f2_jit_fair_aging_deadline__s512 | 13 | 11/6/239 | 0.000000000 | -0.632402500 | 4.023858000 | 0.027651719 | -41 | True |

## Authorization

Selected by validation only: `J7_TEACHER_CF_AFFINE`.

The artifact is a research fixed-workload candidate only. Non-finite, out-of-contract, or candidate-count OOD input falls back to J2; FIFO is used only for a finite in-contract score tie. Native feature/score parity, explicit research grants, coverage and override caps, kill switch, starvation/safety shield, and real learned closed-loop evidence remain mandatory. Production authorization is false because the bounded-local rollout gate fails.
