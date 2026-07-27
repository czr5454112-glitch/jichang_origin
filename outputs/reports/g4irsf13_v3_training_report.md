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
| V0_residual_linear | 0.6146 | 0.7109 | 1.0000 | 0.2492 | 0.2019 | 0.4479 |
| V1_residual_pairwise_logistic | 0.6597 | 0.7448 | 1.0000 | 0.2305 | 0.1990 | 0.4766 |
| V2_residual_listwise | 0.6042 | 0.7031 | 1.0000 | 0.2486 | 0.2442 | 0.4401 |
| V3_residual_tiny_mlp | 0.6910 | 0.7682 | 1.0000 | 0.1855 | 0.1703 | 0.5052 |
| V4_residual_feature_pruned_mlp | 0.6771 | 0.7578 | 1.0000 | 0.2034 | 0.1278 | 0.4948 |
| V5_best_plus_calibrated_risk_head | 0.7396 | 0.8047 | 1.0000 | 0.1882 | 0.1450 | 0.6875 |

The preselected offline diagnostic candidate is `V1_residual_pairwise_logistic`. These numbers measure
agreement with a bounded same-state Level-A projection and F2 preservation;
they are not evidence that TTH improves.
Positive-residual precision and harmful-residual recall include support
counts in the CSV; a value with zero support is not presented as causal
evidence.

V5's risk target is model-specific harm, not hard-cohort membership: the raw
base residual misses the Level-A target while the frozen scorer would have
selected it. The fresh audit contains
`85` positive and
`299` negative risk examples. The risk
classifier is fit on `train`; its affine probability calibration and fallback
threshold are fit on `validation`; the fresh audit is evaluation-only.

Hyperparameters were selected only on `train` + `validation`. A preliminary
aggregate read contaminated the old `test` split, so it is quarantined as
development evidence. The separate `384`-decision,
raw-bag-isolated audit partition is never read by fitting, calibration,
thresholding, or model selection; it is evaluated only after those choices
are frozen. The exact probe rows are in
`g4irsf13_v3_hyperparameter_selection.csv`.

## Feature and identity ablation

`g4irsf13_v3_feature_ablation.csv` contains queue, timing, topology,
credit/fault, storage-leg, pruned-feature, and node-ID diagnostics. The main
models contain no absolute node ID. The with-node-ID row is diagnostic only
and is never exported as a policy candidate.

## Label boundary

V0-V5 rankers use only authorised Level-A same-state one-step targets;
abstentions fall back to the observed successful F2 action. V5 additionally
uses the model-specific Level-A harm definition above for risk supervision.
The Stage-B hard/easy flag remains a reporting slice only. Stage-B v2
disagreements lack matched runtime-state counterfactual replay, so the v2
action, `label_source`, confidence, future dependency, and post-hoc bag delta
are excluded from feature vectors and never become a Level-B/C causal target.

## Immutable model hashes

- `V0_residual_linear`: `de3099a0060c1ce9a8ef61c828d1697d32472814f2bb96db9b4ce0d46d9008fe`
- `V1_residual_pairwise_logistic`: `b7cee5b0af2b7532948d8151f25ad02df6cb5ddc58be0bee66c8d0a04b99e4b1`
- `V2_residual_listwise`: `824aa8f8b5674b45e6c3ff635a249ae2dcfdd3dcc820303449628a19fc84bf3e`
- `V3_residual_tiny_mlp`: `3f11ed8b9e79fd2dc60dc268c7a45e0d75a66ebab4721c3800b4156c3d311e4a`
- `V4_residual_feature_pruned_mlp`: `a7b1880b4dc2c4eee121961f6b9764e3fe273d0c4237ce0525d71491bd9448ec`
- `V5_best_plus_calibrated_risk_head`: `70a30954dba09c623d9e5710059eee13a3fe85e08f2714725fbbfe1084cc2db9`

## Promotion decision

- Offline Level-A gate: `FAIL` under pairwise >= 0.55, top-1 >= 0.50,
  high-confidence harmful <= 0.02, and ECE <= 0.15.
- Full-outcome/TTH corrective contribution: NOT DEMONSTRATED.
- 144 -> 512 -> 2048 -> 8192 -> full closed loop: NOT_RUN.
- Strict win over F2 and frozen v2-safe: NOT_RUN.
- Runtime activation: forbidden.
