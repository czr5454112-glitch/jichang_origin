# G4IRSF7 Java Release Semantics Report

Date: 2026-07-06
Branch: `codex/czr005-rewrite`
artifact_generation_head: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
committed_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
remote_head_at_generation: `f7772c1f535f2ceaca6c4c77d3acd5fb452b1d12`
new_model_training: false
runtime_full_cie_astar_fallback: false
teacher_path_or_future_schedule_leakage: false
legacy_java_modified: false
real_main_map_modified: false

| Evidence | Java Semantics | No-A* Mapping | Risk |
| --- | --- | --- | --- |
| task_list_per_source_queue | Raw input rows are split by source into per-source ArrayList queues. | JSONL stream is globally sorted by attempt_time inside C++ replay. | global continuous release can differ from Java per-source queue gating. |
| early_bag_split | Early bags create storage-in to node 47 and storage-out from node 52 at STD-2700. | Processed JSONL has storage_in/storage_out with same task_id. | must sum both segments and exclude storage dwell. |
| sort_function | Comparator truncates sub-second differences, so ordering within <1s ties is stable/list-order dependent. | C++ sorts by exact pass_time, task_id, segment_id. | minor ordering differences can affect queue tails. |
| epoch_release_gate | At integer epoch, a source queue head is eligible when pass_time-epoch < 1. | Current replay releases at exact floating pass_time. | Java can release fractional pass_time tasks up to <1s earlier. |
| one_per_source_per_epoch | Each source emits at most one new task per epoch. | Current replay can ingest many same-source rows with identical pass_time. | storage-out source 52 tails can be counted as source_retry/wait in no-A* THT. |
| new_task_start_time | New task path planning starts at epoch, not original floating pass_time. | Current replay starts at pass_time. | release time and THT denominator must be declared explicitly. |
| unfinished_retry | Unfinished new tasks retry in a FIFO list after release. | No-A* runtime has no full Java active-unfinished queue proxy. | cannot claim full Java/CIE parity. |
