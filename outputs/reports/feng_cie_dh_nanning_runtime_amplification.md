# Feng-environment CIE-DH Nanning runtime amplification

Status: `VALIDATED_DIAGNOSTIC`, not an algorithm-quality metric and not a
claim about Feng's unavailable original CIE-DH implementation.

## Matched observation

The comparison uses the same frozen reconstructed Java executable, seed
`104729`, load `1x`, raw-bag denominator `28,506`, and host. Only the map and
its byte-audited projected workload differ. Both runs use the declared
`98,259 s` observation horizon; map2 finishes its full population early at
`82,150.2 s`, whereas Nanning reaches the horizon with an incomplete
population.

| metric | map2 1x | Nanning 1x | Nanning / map2 |
|---|---:|---:|---:|
| simulator wall time | 45.091 s | 26,275.911 s | **582.73x** |
| route decisions | 5,845,131 | 4,875,901,927 | **834.18x** |
| hold count | 8,013,264 | 5,059,851,081 | **631.43x** |
| stopped ticks | 2,504,200 | 184,470,586 | 73.66x |
| peak active segments | 591 | 18,908 | 31.99x |
| peak edge occupancy | 356 | 797 | 2.24x |
| completed raw bags | 28,506 | 12,696 | 0.4454x |

Therefore, “more than 800 times slower” is not the precise wall-clock claim.
The directly measured wall-clock amplification is `582.73x`; `834.18x` is the
increase in route-decision-loop executions. The distinction matters because
wall time also depends on JVM and host scheduling, while decision counts are
native state-machine work counters.

## Mechanistic interpretation

The partial Java reconstruction advances through synchronous
snapshot–plan–resolve–commit ticks. Under map2 1x it completes all bags and
the active population drains. Under the Nanning port, unresolved congestion
keeps a much larger active population resident until the fixed horizon. The
runner repeatedly rebuilds occupancy snapshots and evaluates local route or
hold decisions for those active states. The 31.99x peak-active increase,
together with prolonged residence, produces billions of decision and hold
operations.

This evidence supports an engineering diagnosis of pathological computational
scaling for the unchanged partial state machine on Nanning. It does **not**
establish that Feng's original CIE-DH had this runtime, because its source and
full node-handoff semantics were not recovered. It also must not be used as a
replacement performance objective: the paper comparison remains completion,
on-time count, full-population latency when eligible, tail latency, tardiness,
backlog, fairness, and recovery under the frozen business protocol.

## Evidence identity

- map2 summary SHA-256:
  `27b90000073f80ca71880983be515f62bbd53a27e63d282215fe28850ce0c5b4`;
- Nanning summary SHA-256:
  `20936d244e8070ecf99391c817d8b70539bc35564807d1fdbde1995b71287658`;
- reconstruction source bundle SHA-256:
  `99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8`;
- compiled class bundle SHA-256:
  `d611967f0433dfc08f67d92c89e9b13dcb5b8ac5ace3d3abec9c098dba360286`.

The exact numeric rows are in
`outputs/tables/feng_cie_dh_nanning_runtime_amplification.csv`.
