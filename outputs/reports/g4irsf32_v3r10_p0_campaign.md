# G4IRSF32 V3R10 source-aware shadow P0 evidence

Status: `NO_GO_V3R10_P0_SYNTHETIC_VALIDATION`

P1 review authorized: `False`

Control revision: `G4IRSF32_V3R7_MINIMAL_PREARRIVAL_OVERLAP_NANNING_P0_ADDENDUM_20260828`

Synthetic artifact SHA-256: `4dc2d96542cdb4e9ba6a25bfefac531f8358aad82bcbc948f51fb6e8d9c18957`
Nanning shadow content SHA-256: `None`

## Ordered phases

1. Control/identity preflight: `PASS`
2. Synthetic Stage 0/1 freeze and selector deep replay: `NO-GO/NOT-RUN`
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
- `after_nanning_shadow`: `NO-GO/NOT-RUN`

## Problems and handling

- `synthetic` / `SelectionError`: synthetic.stage0.cases[1].off.global_service service-count node identity is invalid
- Full append-only issue/root-cause/remediation history: [G4IRSF32 execution ledger](../../docs/G4IRSF32_execution_ledger.md) (SHA-256 `15d353462c7dc29ae353b6d73310a9701d29e6a86e526b9ba8c395640bc61b96`).
