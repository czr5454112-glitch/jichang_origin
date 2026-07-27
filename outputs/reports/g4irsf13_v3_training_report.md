# G4IRSF13 v3 Residual Training Report

Status: `OFFLINE_LEVEL_A_EVALUATED_FAIL`.
Closed loop remains `NOT_RUN`.

The six requested model families were trained deterministically on real
candidate/action rows. Every model adds a residual clipped to
`[-4.0, +4.0]` to the frozen G4E cost. V5 wraps the
validation-selected base model with a calibrated local risk head; when its risk
threshold fires, the residual is exactly zero and the frozen scorer decides.

## Fresh raw-bag-isolated audit test

| Model | Pairwise | Top-1 | Top-2 | High-conf wrong | ECE | F2 preserved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V0_residual_linear | 0.7760 | 0.7760 | 1.0000 | 0.1564 | 0.0963 | 0.7682 |
| V1_residual_pairwise_logistic | 0.7943 | 0.7943 | 1.0000 | 0.1554 | 0.1079 | 0.7031 |
| V2_residual_listwise | 0.8021 | 0.8021 | 1.0000 | 0.1549 | 0.1032 | 0.7057 |
| V3_residual_tiny_mlp | 0.7891 | 0.7891 | 1.0000 | 0.1608 | 0.1160 | 0.7240 |
| V4_residual_feature_pruned_mlp | 0.7734 | 0.7734 | 1.0000 | 0.1506 | 0.1184 | 0.7604 |
| V5_best_plus_calibrated_risk_head | 0.6641 | 0.6641 | 1.0000 | 0.3554 | 0.3094 | 1.0000 |

The preselected offline diagnostic candidate is `V1_residual_pairwise_logistic`. These numbers measure
agreement with a bounded same-state Level-A projection and F2 preservation;
they are not evidence that TTH improves.
Positive-residual precision and harmful-residual recall include support
counts in the CSV; a value with zero support is not presented as causal
evidence.

Hyperparameters were selected only on `train` + `validation`. A preliminary
aggregate read contaminated the old `test` split, so it is quarantined as
development evidence. The final `384`-decision audit
cohort was extracted from previously unused F2 decisions after
hyperparameters were frozen and was not used for model selection. The exact
probe rows are in `g4irsf13_v3_hyperparameter_selection.csv`.

## Feature and identity ablation

`g4irsf13_v3_feature_ablation.csv` contains queue, timing, topology,
credit/fault, storage-leg, pruned-feature, and node-ID diagnostics. The main
models contain no absolute node ID. The with-node-ID row is diagnostic only
and is never exported as a policy candidate.

## Label boundary

V0-V5 use only authorised Level-A same-state one-step targets; abstentions
fall back to the observed successful F2 action. Stage-B v2 disagreements
lack matched runtime-state counterfactual replay, so the v2 action,
`label_source`, confidence, future dependency, and post-hoc bag delta are
excluded from feature vectors and never become a Level-B/C causal target.

## Immutable model hashes

- `V0_residual_linear`: `65646f80e79486a0e8da6572dd3b0992d28cba94c1d89f214f803c19a44099d0`
- `V1_residual_pairwise_logistic`: `7f448da48401a034758906b81347c8cf382648b2c9d7cb5200e140fa8ea882d4`
- `V2_residual_listwise`: `83caa22a71dcedd9cf27f69df8438281b7019957181f6ffb0d5058c3e1fd9afc`
- `V3_residual_tiny_mlp`: `cd546979a5d06cffb61b10375724dab5d54df091c759ab6f11a2da2f3ed3eb5e`
- `V4_residual_feature_pruned_mlp`: `3d2590b201ed3f38b8e8056baf6d3aa119cc2a37c047ef594fbe48110b58faac`
- `V5_best_plus_calibrated_risk_head`: `2318d5db5a3429fe93f44c0225ed2ccd67296d86881b4eacfce50588ed7f5acf`

## Promotion decision

- Offline Level-A gate: `FAIL` under pairwise >= 0.55, top-1 >= 0.50,
  high-confidence harmful <= 0.02, and ECE <= 0.15.
- Full-outcome/TTH corrective contribution: NOT DEMONSTRATED.
- 144 -> 512 -> 2048 -> 8192 -> full closed loop: NOT_RUN.
- Strict win over F2 and frozen v2-safe: NOT_RUN.
- Runtime activation: forbidden.
