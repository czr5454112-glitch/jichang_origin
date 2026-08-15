# G4IRSF24 Dense Transition Data

Status: `COLLECTED_AND_FIT`.

- Transitions contain only local physical state and duration fields; task and decision identities are excluded.
- Absolute t0/t1 are used only for chronological ordering and split boundaries; no timestamp is stored in a runtime artifact or used as a model feature.
- Each dense source run stores one deterministic task-id shard. `trace_complete=true` means that requested shard was fully retained; paired complementary shards form the reported population, not one unsharded per-run trace.
- Validation selects at most one candidate per family; the chronological test tail is evaluated only after fitting and is reported separately.
- Best learned held-out action-score proxy MAE is 7.476283s versus its zero-residual S4 proxy 2.596602s; this is negative non-stationarity evidence, not a learning win.
- Compact edge-goal evidence: `artifacts/datasets/g4irsf24_transition_compact.jsonl`.

| Section | Item | Status | Transitions | Coverage | MAE (s) |
| --- | --- | --- | --- | --- | --- |
| campaign | all | COLLECTED_AND_FIT | 1016981 | NOT_MEASURED | NOT_MEASURED |
| source | 1x_r0 | PASS | 169861 | NOT_MEASURED | NOT_MEASURED |
| source | 1x_r1 | PASS | 169576 | NOT_MEASURED | NOT_MEASURED |
| source | 2x_r0 | PASS | 339176 | NOT_MEASURED | NOT_MEASURED |
| source | 2x_r1 | PASS | 338368 | NOT_MEASURED | NOT_MEASURED |
| candidate | DLP_EWMA_D | MEASURED | NOT_MEASURED | 1.0000 | 12.210 |
| candidate | DLP_EWMA_A | MEASURED | NOT_MEASURED | 1.0000 | 13.473 |
| candidate | DLP_EWMA_B | MEASURED | NOT_MEASURED | 1.0000 | 13.473 |
| candidate | DLP_EWMA_C | MEASURED | NOT_MEASURED | 1.0000 | 13.473 |
| candidate | DLP_TD_B | MEASURED | NOT_MEASURED | 1.0000 | 13.473 |
| candidate | DLP_TD_A | MEASURED | NOT_MEASURED | 1.0000 | 14.346 |
| candidate | DLP_TD_D | MEASURED | NOT_MEASURED | 0.9999 | 12.210 |
| candidate | DLP_TD_C | MEASURED | NOT_MEASURED | 0.9999 | 13.473 |
