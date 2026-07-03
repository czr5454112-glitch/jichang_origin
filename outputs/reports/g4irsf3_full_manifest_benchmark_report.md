# G4IRSF3 Full-Manifest Benchmark Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Result

| Measured Tasks | Planned | Remaining Failed | Node Conflicts | Full A* | No-A* s | Static A* Proxy s |
| --- | --- | --- | --- | --- | --- | --- |
| 348824 | 348098 | 726 | 0 | 0 | 1022.242 | 2.913 |

## Streaming Status

| Mode | Status | Continuity? | Reason |
| --- | --- | --- | --- |
| chunked_full_manifest_reset_state | MEASURED_FULL_TASK_COVERAGE | False | chunk state resets; useful coverage benchmark but not a continuous 348824-task simulation |
| full_manifest_8x_streaming_single_call | BLOCKED_API_AND_RESOURCE_BUDGET | False | current pybind runtime does not expose reservation/traffic memory import-export; single-call run is projected from chunks and not promoted |

This is a full task-coverage benchmark when all chunks are present, but it is not a continuous simulation because each chunk starts with empty reservation and traffic memory. That limitation is kept as the main blocker.
Failed task case details, when any exist, are written to `outputs/tables/g4irsf3_full_manifest_failed_task_cases.csv`.

reused_existing_chunk_table: `True`
