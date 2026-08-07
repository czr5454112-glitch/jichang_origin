# G4IRSF19 live frontier and cost

This report replaces the 4× external-timeout black box with native, unfinalized progress snapshots. All rows use the real G18 fixed-map scale stream, frozen local controls, and J2 merge timing.

| scale | scorer | status | events/s | complete/s | sim/wall | retry/s | coalesced/s | CPU/wall | RSS sample MiB | preliminary signal |
|---:|:---:|:---|---:|---:|---:|---:|---:|---:|---:|:---|
| 1× | S1 | COMPLETE | 234365.773 | 2088.537 | 3933.526 | 0.000 | 5858.613 | 0.979 | 1173.684 | MIXED_EVENT_LOAD_NO_SINGLE_COUNTER_DOMINATES |
| 2× | S1 | BOUNDED_PROGRESS | 167521.963 | 1095.867 | 1031.612 | 0.000 | 10541.161 | 0.987 | 246.281 | MIXED_EVENT_LOAD_NO_SINGLE_COUNTER_DOMINATES |
| 4× | S1 | BOUNDED_PROGRESS | 68305.885 | 296.590 | 443.211 | 0.000 | 3568.683 | 0.983 | 453.832 | MIXED_EVENT_LOAD_NO_SINGLE_COUNTER_DOMINATES |

## Interpretation boundary

Event-type ratios plus retry/wakeup slopes are preliminary associations, not a causal CPU attribution. This runner does not implement disk checkpoints or restart, and it does not expose CPU categories. RSS values are endpoint samples, not peaks. A BOUNDED_PROGRESS row is intentionally not finalized and must not be ranked as a completed performance win.
