# G4IRSF14 matched-state clone blocker audit

- Audit schema: `czr005.g4irsf14.matched_state_clone_blocker_report.v1`
- Status: `PARTIAL_WITH_EXPLICIT_BLOCKER`
- Formal pass claimed: `false`
- Formal v3 schema claimed: `false`
- Causal label count: `0`
- Bundle generation ID: `066f4fbce18d45eef1fb27cee5e26bf5a22365f62dbe0f7f4ebb4a8687aa7aa3`
- Census self SHA-256: `8f4592c9745058301a0cd4cf4135d0ce003ce031a3ec61af0989fb93efc466a9`

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
| `outputs/tables/g4irsf14_opportunity_census.json` | `d66ad256c7f6ef7b44642ed1715b9bf01d609e191eba308f21c06367710e56d7` |
| `outputs/tables/g4irsf14_clone_fidelity.csv` | `1143b4488fce1f6db355c9212a0423757accceabbed69a91a1de10e99fe951b0` |
| `outputs/tables/g4irsf14_causal_interventions.csv` | `283366d74bc021c90a6f3a9a769243a6e7825f0cb3b51b97cde886fe67eb3451` |
| `outputs/tables/g4irsf14_causal_component_ledger.csv` | `8cc00a2483fc7ac31ab801de9e4c973e090a6f2b4da9cdb8dbd1b9ad797e62b8` |

The clone manifest is published last as the transaction commit marker and binds this report plus every table above.
