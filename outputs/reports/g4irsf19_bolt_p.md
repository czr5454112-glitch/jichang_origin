# G4IRSF19 minimal executable BOLT-P path

Status: **COMPLETE**.

Workers execute independent pure proposal/counterfactual groups in separate processes. Results are aggregated in plan order. This is not parallel mutation or commit inside one event-runtime instance.

P=1 deterministic replay parity: **True**.
All requested process counts match P=1: **True**.

| P | groups | proposed | evidence commits | failures | stale | conflicts | worker processes | wall seconds | P=1 parity |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 274.199513 | True |

## Interpretation

The native mode reuses G15's exact in-memory checkpoint/clone pair runner. Because checkpoints are not serialized, each worker deterministically replays the prefix for its independent group. Canonical aggregation is executable and measured; shared-runtime parallel discrete-event commit remains future work.
