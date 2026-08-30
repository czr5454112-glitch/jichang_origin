# G4IRSF32 V3R11 source-aware shadow P0 evidence

Status: `NO_GO_V3R11_NANNING_P0_REAL_MIXED_ORIGIN_NOT_OBSERVED`

P1 review authorized: `False`

Control revision: `G4IRSF32_V3R7_MINIMAL_PREARRIVAL_OVERLAP_NANNING_P0_ADDENDUM_20260828`

Synthetic artifact SHA-256: `b7d55f1c52a245a74454cc5dba268dc2b72eab946030c5a219722227d39d76d2`
Nanning shadow content SHA-256: `None`

## Ordered phases

1. Control/identity preflight: `PASS`
2. Synthetic Stage 0/1 freeze and selector deep replay: `PASS`
3. Nanning G32 shadow: `NO-GO/NOT-RUN`

## Hard gates

- [x] `candidate_executor_recorded`
- [x] `v3r7_control_schema_exact`
- [x] `v3r7_control_protocol_exact`
- [x] `v3r7_control_revision_exact`
- [x] `v3r7_control_status_exact`
- [x] `control_artifact_deep_valid`
- [x] `explicit_g32_binary_exact`
- [x] `clean_committed_implementation`
- [x] `source_bundle_self_consistent`
- [x] `g32_build_head_matches_clean_head`

## Integrity checkpoints

- `start`: `PASS`
- `after_synthetic_freeze`: `PASS`
- `after_nanning_shadow`: `PASS`

## Problems and handling

- `nanning_shadow` / `CampaignError`: Nanning shadow gate returned NO_GO_V3R11_NANNING_P0_REAL_MIXED_ORIGIN_NOT_OBSERVED
- Full append-only issue/root-cause/remediation history: [G4IRSF32 execution ledger](../../docs/G4IRSF32_execution_ledger.md) (SHA-256 `aa513692c20aeb2f57607a994ea10a88bc5fcd13dfe77f7a8335fb0ba51ea687`).
