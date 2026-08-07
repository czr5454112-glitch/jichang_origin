# G4IRSF19 live frontier and cost

This report replaces the 4× external-timeout black box with native, unfinalized progress snapshots. All rows use the real G18 fixed-map scale stream, frozen local controls, and J2 merge timing.

| scale | scorer | status | events/s | complete/s | sim/wall | retry/s | coalesced/s | CPU/wall | RSS sample MiB | preliminary signal |
|---:|:---:|:---|---:|---:|---:|---:|---:|---:|---:|:---|
| 1× | S4 | COMPLETE | 238125.995 | 2137.602 | 4025.935 | 0.000 | 5750.538 | 0.989 | 1231.359 | MIXED_EVENT_LOAD_NO_SINGLE_COUNTER_DOMINATES |
| 2× | S4 | COMPLETE | 209067.760 | 1600.922 | 1508.277 | 0.000 | 11997.350 | 0.990 | 1661.781 | MIXED_EVENT_LOAD_NO_SINGLE_COUNTER_DOMINATES |
| 4× | S4 | BOUNDED_PROGRESS | 96895.527 | 468.284 | 476.843 | 0.000 | 6564.309 | 0.975 | 454.273 | MIXED_EVENT_LOAD_NO_SINGLE_COUNTER_DOMINATES |

## Interpretation boundary

Event-type ratios plus retry/wakeup slopes are preliminary associations, not a causal CPU attribution. This runner does not implement disk checkpoints or restart, and it does not expose CPU categories. RSS values are endpoint samples, not peaks. A BOUNDED_PROGRESS row is intentionally not finalized and must not be ranked as a completed performance win.
