# G4IRSF25 native scale

This report contains only native G25 rows. The independent HCA scale report may be cross-referenced later; no HCA or G24-static value is synthesized here.
Bounded 4x rows report progress counters, mutations, and safety. Their processed-attempt TTH distribution remains `NOT_MEASURED` unless a separate complete-population protocol supplies it.

## Balanced full 1x/2x status

| policy | 1x evidence | 1x safety | 2x evidence | 2x safety |
|---|---|---|---|---|
| S4 | `MEASURED_BALANCED_REPEATS` | `PASS` | `MEASURED_BALANCED_REPEATS` | `PASS` |
| T0 | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` |
| L1 | `MEASURED_BALANCED_REPEATS` | `PASS` | `MEASURED_BALANCED_REPEATS` | `PASS` |
| L2 | `MEASURED_BALANCED_REPEATS` | `PASS` | `MEASURED_BALANCED_REPEATS` | `PASS` |
| L3 | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` |

## Bounded 4x progress

| policy | window | status | released/requested | completed/requested | backlog | completion | events/completed | mutations | safety | mean/p95/p99/max TTH s |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|
| S4 | 60s | `BOUNDED_PROGRESS` | 39429/174412 | 25218/174412 | 14211 | 14.459% | 176.717 | 0 | `PASS` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| S4 | 180s | `BOUNDED_PROGRESS` | 71203/174412 | 50584/174412 | 20619 | 29.003% | 193.043 | 0 | `PASS` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| T0 | 60s | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| T0 | 180s | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| L1 | 60s | `BOUNDED_PROGRESS` | 39278/174412 | 25724/174412 | 13554 | 14.749% | 180.884 | 3127 | `PASS` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| L1 | 180s | `BOUNDED_PROGRESS` | 73785/174412 | 56696/174412 | 17089 | 32.507% | 187.259 | 5030 | `PASS` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| L2 | 60s | `BOUNDED_PROGRESS` | 40637/174412 | 26826/174412 | 13811 | 15.381% | 178.339 | 3435 | `PASS` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| L2 | 180s | `BOUNDED_PROGRESS` | 73275/174412 | 55377/174412 | 17898 | 31.751% | 188.169 | 4677 | `PASS` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| L3 | 60s | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |
| L3 | 180s | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` | `NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED`/`NOT_MEASURED` |

For incomplete or absent full populations, latency and tail claims remain literal `NOT_MEASURED`.
