# G4IRSF19 process-isolated paired rollout farm

Status: **`COMPLETE_DETERMINISTIC`**.

This benchmark runs each fixed pair in one fresh process: J2/S1 first,
then J2/S2 on the same G18 ladder prefix. P changes concurrency only.

| P | Repeat | Jobs | Wall s | Speedup | Efficiency | Groups/hour | Semantic = P1 | Retries | Failures |
|---:|---:|---:|---:|---:|---:|---:|:---:|---:|---:|
| 1 | 1 | 8 | 105.699 | 1.000 | 1.000 | 272.5 | yes | 0 | 0 |
| 2 | 1 | 8 | 56.726 | 1.863 | 0.932 | 507.7 | yes | 0 | 0 |
| 4 | 1 | 8 | 32.139 | 3.289 | 0.822 | 896.1 | yes | 0 | 0 |
| 8 | 1 | 8 | 20.145 | 5.247 | 0.656 | 1429.6 | yes | 0 | 0 |
| 1 | 2 | 8 | 104.352 | 1.000 | 1.000 | 276.0 | yes | 0 | 0 |
| 2 | 2 | 8 | 53.090 | 1.966 | 0.983 | 542.5 | yes | 0 | 0 |
| 4 | 2 | 8 | 31.333 | 3.330 | 0.833 | 919.2 | yes | 0 | 0 |
| 8 | 2 | 8 | 19.595 | 5.325 | 0.666 | 1469.8 | yes | 0 | 0 |

## Claim boundary

- This proves only process-isolated replica throughput and output determinism.
- The replicas repeat one fixed workload; they are not independent learning support.
- S1/S2 resources are excluded before semantic equality is evaluated.
- No production policy promotion is implied.
