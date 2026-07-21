# G4IRSF11 Source and Runtime Identity Audit

Generated: `2026-07-21`.

| Metric | Value |
| --- | --- |
| Processed source segments | 3072 |
| Unique original task IDs | 1986 |
| Original task IDs shared by multiple segments | 1022 |
| Extra segments sharing an original task ID | 1086 |
| Maximum segments per original task ID | 5 |
| Observed runtime identities | 3072 |
| Observed original segment identities | 3072 |
| Runtime identity aliases | 0 |

Status: `PASS`.

Original `task_id` values are preserved exactly and are never rewritten to hide repeated IDs. The event runtime uses `metadata.runtime_bag_id` as an internal identity scoped to one run; the audit rejects either one internal ID aliasing two original `(task_id, segment_id)` pairs or one original segment changing internal IDs.

The source counts cover the complete input task file. Runtime identity counts cover every committed decision present in the validated trace shards; trace shard completeness is reported separately and cannot be inferred from this PASS.
