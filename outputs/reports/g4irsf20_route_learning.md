# G4IRSF20 Route learning decision

Status: **`PRIMARY_PAIR_DATA_CONTRACT_NO_GO`**. No Route policy was exported.

## Evidence contract

- Exact primary-pair groups: 5,022
- Candidate-action rows: 10,044
- Raw-task split groups: 4,630
- Train / validation / audit groups: 3,505 / 763 / 754
- Cross-split group contamination: 0
- Labels: 102 beneficial, 28 neutral, 4,892 harmful
- Full legal action set labeled: no
- WAIT labeled: no
- Source distribution: protected 1x only

The target is affected runtime-segment completion. H_system raw-bag TTH is a
diagnostic/veto signal; it is not substituted for the primary label.

## Three-family comparison

No family passes every grouped-audit promotion gate.

| Exploratory result | Audit applied | Beneficial | Harmful | Mean advantage vs S4 | LCB90 | Decision |
|---|---:|---:|---:|---:|---:|---|
| tiny MLP, F2 | 3 | 3 | 0 | +0.013793 s | +0.000136 s | support 3 < 5 |
| set scorer, F2 | 2 | 2 | 0 | +0.011141 s | -0.001809 s | support and LCB fail |
| linear residual, all F-groups | 0 | 0 | 0 | 0.000000 s | 0.000000 s | no selective mutation |

The exploratory ordering is tiny MLP, set scorer, then linear residual. It is
not a promotion ranking: the strongest row has insufficient support and the
supervision contract omits legal alternatives and WAIT.

## Feature evidence

F2 (S4 core plus current-owner state) is the strongest numerical hint. Its
tiny-MLP audit regret is 0.196464 versus the S4 baseline's 0.210257. F1 does
not improve tiny MLP over F0; F3 applies no selective changes. F4 with two-hop
pressure is worse than F5 without it (-0.005611 s versus -0.000041 s mean
selective advantage, both with negative LCB90). Window trends and ETA summaries
were not present in the native sidecar and were not zero-filled or evaluated.

No controlled alias-collision experiment was run, so no feature group is
claimed to solve state aliasing. A separate standalone MLP was not evaluated;
the score-free set scorer must not be relabeled as that experiment.

## Decision

Keep Source A0 + Route S4 + Merge J2 as the normal-flow decentralized
controller. Retain this dataset and three-family comparison as offline research
evidence. Do not run learned 1x/2x closed loop, reopen Source, or claim gap
closure until exact labels cover every legal next edge and legal WAIT.
