# G4IRSF14 matched-state clone blocker audit

- Audit schema: `czr005.g4irsf14.matched_state_clone_blocker_report.v1`
- Status: `PARTIAL_WITH_EXPLICIT_BLOCKER`
- Formal pass claimed: `false`
- Formal v3 schema claimed: `false`
- Causal label count: `0`
- Bundle generation ID: `a19c406aa5ea5a501f0ed43f220d3b476ab909986f4de2da24e35a8c970d6d3f`
- Census self SHA-256: `9d0da238e0bef3aed5cd12b6a713c6e53d1a0156f1b2abd64a31a528088e555d`

This report is a blocker/audit artifact. It does not contain matched causal labels and cannot satisfy the Stage 14E formal promotion gate.

## Executed evidence

One exact-binary, three-way no-op checkpoint replay established mechanism fidelity for all five replay hashes. Two passive original-1x diagnostic runs established opportunity screening support and live hard-gate evidence. No action-changing matched H_bag or H_system branch was run.

| Intervention | Strict screening support | Prefilter-only rows | Formal matched boundaries | Formal completions | Interpretation |
|---|---:|---:|---:|---:|---|
| I1 source order | 41679 | 0 | 0 | 0 | complete source screening census |
| I2 merge order | 1 | 0 | 0 | 0 | exact native live-eligible boundary count |
| I3 next edge | 19898 | 0 | 0 | 0 | stored-trace lower bound |
| I4 hold/release | 59049 | 0 | 0 | 0 | stored-trace lower bound |
| I5 PIBT trigger | 0 | 1337 | 0 | 0 | prefilter-only rows make no no-benefit claim; strict support starts only when `slice.applicable` constructs the identical ready slice |

## Explicit blockers

- `H_SYSTEM_INTERVENTION_COUNT_IS_ZERO`
- `I5_ZERO_P2_READY_SLICE_INTERVENTION_BOUNDARIES`
- `NO_EXACT_BINARY_ONE_SHOT_I1_I5_INTERVENTION_RERUNS`
- `ORIGINAL_TASK_MINIMUM_2000_MATCHED_INTERVENTIONS_NOT_ESTABLISHED`
- `ZERO_COMPLETE_H_BAG_H_SYSTEM_CAUSAL_LABELS`

## SHA-256 bindings

| Artifact | SHA-256 |
|---|---|
| `outputs/tables/g4irsf14_opportunity_census.json` | `365d2a8f860944616f5e7199be2c3c86b3d07dc743ba793b978b0fedf4586de3` |
| `outputs/tables/g4irsf14_clone_fidelity.csv` | `c1e2e590f9be020ef43671088e3f8feba347b6708917cb09d15e1f9747adb1a5` |
| `outputs/tables/g4irsf14_causal_interventions.csv` | `283366d74bc021c90a6f3a9a769243a6e7825f0cb3b51b97cde886fe67eb3451` |
| `outputs/tables/g4irsf14_causal_component_ledger.csv` | `f7b05a0b95e2332d6317c64684211b7d9079e74e1f753c4c5ea6b4a3ea29dbd7` |

The clone manifest is published last as the transaction commit marker and binds this report plus every table above.
