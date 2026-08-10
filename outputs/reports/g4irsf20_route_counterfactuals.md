# G4IRSF20 Route counterfactual campaign

This campaign reuses the G15 exact same-state clone engine with the `G20_S4_J2`
profile. Sampling is a simple event-order/long-wait stratification; it does not
introduce a hash-ranked sample or a separate checksum manifest.

Selected compact census rows are passed back as five-field deferred targets.
The former full descriptor-materialization pass is not run.

- Full-census I3 population: 174,868
- Screened candidates submitted: 7,500
- Screened long-wait candidates: 5,093
- Screened H_system candidates: 750
- Complete eligible pairs: 5,022
- Eligible long-wait pairs: 3,147
- Eligible H_system pairs: 520
- Pair failures/incomplete: 2,478
- Labels: beneficial=102, neutral=28, harmful=4,892

`NOT_APPLICABLE_ACTION_PRECONDITION_FAILED` means the cheap census candidate
was removed by exact replay screening. It is not a hard-safety failure and it
does not enter the compact training rows.

The published JSONL contains the complete pre-action local observation set and
one exact S4-versus-primary-alternative label per sampled boundary. It does not
claim that every legal edge or WAIT is labeled. The primary label is affected
runtime-segment completion, not a complete raw-bag or order objective. H_system
raw-bag TTH is a diagnostic; raw-bag or order-level benefit is not yet proven.
Absolute IDs are split/trace metadata and are not model features.
No future route, global reservation scan, full A*, or post-hoc outcome is
present in the observation sidecar. The source distribution is protected 1x.
