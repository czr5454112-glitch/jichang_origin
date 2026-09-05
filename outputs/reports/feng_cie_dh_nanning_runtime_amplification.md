# Feng-environment CIE-DH Nanning runtime amplification

Scientific validity: `INVALIDATED_ZERO_THROUGH_STATE_MACHINE_BUG`.
The original counters, timings, hashes and execution outcomes below are
preserved as observations of a defective program. The earlier
`VALIDATED_DIAGNOSTIC` performance interpretation is withdrawn. This is not
valid evidence of normal congestion scaling or of Feng's original CIE-DH.

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

## Corrected interpretation (2026-09-05)

The old zero-through intermediate-node branch starts an instantaneous service
but fails to release the upstream edge and enter the subsequent transfer
timer. It can repeat that start every tick and count it as progress. Nanning
has 22 zero-through nodes with both incoming and outgoing edges; map2's 13
zero-through nodes are endpoints. The old Nanning completion, moving/stopped
counts, route decisions and runtime are consequently contaminated.

`834.18x` remains the arithmetic ratio of this Java reconstruction's Nanning
route-decision count to its map2 count; `582.73x` is the corresponding
simulator wall-time ratio. Neither ratio is a G31-over-CIE-DH speedup. The
earlier attribution to normal congestion or scalable routing behavior is
withdrawn. A matched full-population pre/post comparison would be needed to
quantify how much of the approximately 44% completion and runtime difference
the bug explains; the old counters alone cannot establish that it explains
all differences.

The machine-readable exclusion and unchanged-file hashes are recorded in
`outputs/runtime/cie_external_baseline_robustness/scientific_validity_20260905.json`.
Corrected execution must use a separate output/version directory.

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
