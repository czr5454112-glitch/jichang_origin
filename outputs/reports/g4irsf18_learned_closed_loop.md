# G4IRSF18 learned merge closed-loop coverage ladder

Decision: **`RESEARCH_LADDER_EVIDENCE_ONLY_PRODUCTION_FALSE`**.

Every learned row is paired with a same-prefix J2 control. Proposal is not ownership: only native applied decisions count, and a mutation additionally requires a feature-distinct action. Production authorization is false for every job and for this report.

| Prefix | Telemetry | Coverage | Eligible | Proposal | Applied/ownership | Distinct mutation | Fallback J2/coverage/override/starvation | Safety | TTH mean delta | P95 delta | P99 delta | Source delta | Merge delta | Network delta | Event delta |
|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 144 | evidence_trace | 100% | 0 | 0 | 0/0 | 0 | 0/0/0/0 | True | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| 512 | evidence_trace | 10% | 13 | 13 | 1/1 | 0 | 12/12/0/0 | True | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| 2048 | evidence_trace | 5% | 138 | 138 | 6/6 | 0 | 132/132/0/0 | True | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| 2048 | evidence_trace | 25% | 138 | 138 | 34/34 | 1 | 104/104/0/0 | True | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| 2048 | evidence_trace | 50% | 138 | 138 | 69/69 | 1 | 69/69/0/0 | True | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| 2048 | evidence_trace | 80% | 137 | 137 | 109/109 | 3 | 28/28/0/0 | True | 0.0 | 0.0 | 0.0 | 0.0 | -0.0009118529130867081 | 0.0 | 0 |
| 2048 | evidence_trace | 100% | 137 | 137 | 137/137 | 3 | 0/0/0/0 | True | 0.0 | 0.0 | 0.0 | 0.0 | -0.0009118529130867081 | 0.0 | 0 |
| 8192 | evidence_trace | 100% | 935 | 919 | 919/919 | 44 | 16/0/0/16 | True | 0.0 | 0.0 | 0.0 | 0.0 | -0.035961970191915604 | 0.0 | -6 |
| 43603 | capacity | 100% | 3526 | 3500 | 3500/3500 | 154 | 26/0/0/26 | True | -0.0046534013890777715 | 0.0 | 0.0 | -0.0033589419771296036 | -0.018039048270545477 | -0.0012944594120369857 | 228 |

All fallback counters are retained in the CSV/JSON, including OOD, invalid artifact, score tie, authorization, coverage, per-segment override, starvation, and kill-switch paths. An insufficient eligible denominator is reported rather than converted into a zero-effect success.

This is fixed-workload research evidence only. Both `production_closed_loop_authorized` and native `production_promotion_authorized` remain `false` regardless of ladder outcome.
