# G4IRSF12-K Original Task Generation Audit

Date: 2026-07-23

status: `PASS_WITH_NEGATIVE_GENERATOR_FINDING`
scaled_workload_generated: `false`
runtime_executed: `false`

## Finding

The immutable raw input and processed JSONL exactly reproduce the active Java loader/split rules for all 28,506 bag IDs and 43,603 segments. The original project does **not** contain an active larger-day demand generator: the random initial-task and random-OD code is commented out, while active code consumes static source queues loaded from `inputdata.txt`.

Accordingly, no future scaled input may be called `original_project_generated`. If the gated deterministic protocol is later implemented and passes its audits, the strongest allowed label is `original_rule_replay_scaled_input`.

## Immutable identity

| Artifact | SHA-256 | Status |
| --- | --- | --- |
| legacy/jichang_origin_readonly/inputdata.txt | 0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87 | MATCH |
| data/processed/tasks/inputdata.jsonl | 968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f | MATCH |
| legacy/jichang_origin_readonly/src/RUN/Main.java | af7ba8f8224a480f61e4d4b010d0c6fcf5e8798cccfdf6f298d786ac053bf5af | MATCH |
| legacy/jichang_origin_readonly/src/App/Tasks.java | dd4505e495fd3c0fa737923dca83c9d404fc3b1e3a7ce979e7dd384a57d0948b | MATCH |
| data/processed/maps/map2.json | 9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4 | MATCH |

## Raw schema and audited transformation

Raw header: `ID EntryTime(s) STD(s) star end Unloader Loader`

| Condition | Processed segment rule | Validated count |
| --- | --- | --- |
| `STD - EntryTime < 4800` | one direct segment: raw start -> raw goal at EntryTime | 13,409 bags |
| `STD - EntryTime >= 4800` | storage_in: raw start -> 47 at EntryTime | 15,097 bags |
| same early bag | storage_out: 52 -> raw goal at STD - 2700 | 15,097 bags |

Both segments keep the original integer `task_id`/`pallet_id`; `segment_id` adds `direct`, `storage_in`, or `storage_out`. Therefore bag-level metrics must group by original task ID, not treat 43,603 segments as independent bags.

The conversion was checked row-for-row, including source line, original and processed start/goal, EntryTime, STD, pass time, leg, and segment ID.

## Business labels, physical nodes, and OD

The raw `Loader` labels preserve the seven paper totals: `{"A1": 1176, "B1": 2872, "B2": 5544, "C1": 4533, "C2": 7542, "D1": 2585, "T": 4254}`. The raw `star` field instead yields physical source nodes: `{"0": 3200, "1": 3193, "2": 3199, "3": 4887, "4": 4887, "5": 4886, "53": 4254}`.

The raw `Unloader` label has five values, while the raw goal field uses map nodes 48/49/50. Both label-level and node-level OD mixes must be audited because the processed JSONL does not retain the `Loader`/`Unloader` text columns.

## Active Java release behavior

1. `Main.ReadTaskList` loads `inputdata.txt`, applies the 4,800 s early rule, and adds split storage-out work at node 52 with `pass_time = STD - 2700`.
2. Each per-source list is sorted by `pass_time`; the main loop starts at epoch 8,260 and advances in one-second steps.
3. `Tasks.generate_tasks` considers only the queue head. A source must have no unfinished task from that source, and the head is eligible when `pass_time - epoch < 1`. At most one head is removed from a source during an epoch.
4. The emitted runtime task keeps the source bag ID and goal. The nearby code that would choose a random goal is commented out.
5. Fault and repair events are runtime probability draws over map edges; they are not demand records in `inputdata.txt`. The delay draw block is also commented out. A demand scaler must not invent fault/repair/pass-time values.

## Negative generator finding

No active code derives a new flight schedule, loader/unloader mix, EntryTime, STD, local/transfer split, or larger design day. Existing G4IRSF2 high-flow data was correctly labeled `distribution_preserving_resample`; it is not evidence of an original Java demand generator and is not used to calibrate this multiplier.

## Future protocol, not executed

After every Phase-L gate passes, retain each baseline bag once, allocate only the additional bags across fixed strata using largest remainders, and select donors by SHA-256 order with seed 20260723. Strata include clock hour, Loader, Unloader, physical start/goal, early-split state, and deadline-lead bin. Assign new IDs and reapply the exact Java split rules without time compression.

Before any run, audit hourly and rolling-window arrival shape, business and physical OD shares, early/EBS share and dwell, deadline lead, and static directed route lower bounds. Drift tolerances must be fixed before materialization and cannot turn a sensitivity into a real-demand claim.

Current execution policy: `DESCRIPTORS_ONLY_NO_SCALING_RUN`.
