# G4IRSF17 fixed-map scale benchmark

Business time and compute resources are separate columns. Historical v2-safe/legacy tables are context, not matched E4 promotion comparators.

| Candidate | Load | Status | Mean TTH s | P95 TTH s | Source wait s | Wait>0 % | Wait P95 s | Network s | Events/segment | CPU/event us | Wall s | RSS MB | Hard gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E4_OFF | 1x | COMPLETE | 217.5834 | 270.0540 | 0.2006 | 1.7786 | 0.0000 | 217.3827 | 121.7842 | 5.4171 | 32.0115 | 1403.7734 | True |
| E4_OFF | 2x | COMPLETE | 1388.0057 | 7967.0490 | 985.5425 | 34.6173 | 7089.3375 | 402.4632 | 172.2843 | 10.4082 | 166.5058 | 1836.8320 | True |
| E4_OFF | 4x | HARD_GATE_FAILED | — | — | — | 55.1336 | 786.1875 | — | 114.6710 | 195.2508 | 3983.4641 | 2328.8438 | False |
| E4_OFF | 8x | HARD_GATE_FAILED | — | — | — | 56.0964 | 677.0500 | — | 57.3355 | 325.8320 | 6669.9712 | 2990.5469 | False |
| E4_OFF | 16x | HARD_GATE_FAILED | — | — | — | 41.7746 | 483.7500 | — | 28.6678 | 497.2063 | 10229.0410 | 5174.6406 | False |

Reference tables: `outputs/tables/g4irsf10_v2_safe_high_flow_matrix.csv`

Structured hotspot profile: `outputs/profiles/g4irsf17_scale_hotspots.csv`.
Profiling decision: **`VERIFIED_EVENT_QUEUE_RESERVE_MICRO_OPT`**.
The verified event-priority-queue reserve reduced mean CPU by 3.2863% and mean worker wall time by 2.5787% across two 1x repeats with exact business/safety parity. This bounded initialization optimization does not solve the 4x event-cap failure; source-admission pressure and event amplification remain the scale blockers.
All required fixed-map scale rows now have real interpretable terminal observations. Event-cap capacity censoring occurred at 4x, 8x, and 16x; those rows are not scalability wins.
Queue telemetry: **`PARTIAL_PER_NODE_QUEUE_PEAKS`** (1/5 required rows).
Per-node source/junction queue peaks were not exposed for every required scale row. The evidence supports source-wait and event amplification, but it does not establish a per-node queue-peak bound.

Track status: **COMPLETE**. Censored legacy/new rows are not ranked as winners.
