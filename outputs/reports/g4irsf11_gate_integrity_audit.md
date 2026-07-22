# G4IRSF11 Gate A production evidence audit

Overall production-evidence status: `FAIL`.

This report evaluates the checked-in G4IRSF10 artifacts. Passing function tests are not production evidence and cannot change a failing evidence gate.

## Fixed real map identity

- Path: `data/processed/maps/map2.json`
- Normalized-text SHA-256: `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63`
- Raw-byte SHA-256: `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4`
- Topology mutation allowed: `false`

## Gate results

| Gate | Status | Violations | Evidence rows |
| --- | --- | --- | --- |
| fixed_real_map_identity_and_topology | PASS | 0 |  |
| paper_scenario_exact_set_hash_status | FAIL | 111 | 37 |
| optional_executed_or_explicit_blocker | FAIL | 4 | 17 |
| hard_case_stratified_coverage_and_validity | FAIL | 200004 | 50000 |
| runtime_feature_field_lineage_no_leakage | PASS | 0 |  |

## Explicit historical blockers

- Paper matrix: `FAIL` with `111` violations. The frozen 37 rows lack recorded execution status, executable command, and return code (37 x 3 = 111).
- Optional boundary matrix: `FAIL` with `4` violations. Each of the four boundaries lacks an executed-or-explicit-blocker status.
- Legacy hard-case index: `FAIL` with `200004` violations. It is path/task-derived, lacks legal decision records and sampling provenance, and is not training evidence.
- Runtime field lineage: `PASS`. The actual committed lineage remains a distinct transitive no-leakage gate.

## Claim boundary

Gate A is fail-closed. Historical execution summaries remain useful diagnostics, but they are not promoted to reproducible experiment, optional-boundary, hard-case-training, or CI provenance PASS.
