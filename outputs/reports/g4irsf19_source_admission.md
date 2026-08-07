# G4IRSF19 Source ADMIT/HOLD pressure campaign

The campaign keeps E4/J2/M3, Route S4, R3, P2 and Q0 fixed. A0 disables source admission/backpressure, A1 uses the existing absolute downstream queue penalty, and A2 uses the existing goal-conditioned differential. No model is trained and no native mechanism is added.

| Case | Arm | Safety | Attempts | Admitted | Local HOLD retries | Downstream HOLD retries | Distinct observed HOLD states | Held bags | Mean TTH (s) | Source wait (s) | Events | Delta TTH vs A0 (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| prefix_144 | A0 | True | 144 | 144 | 0 | 0 | 0 | 0 | 10212.3807 | 1.2743 | 14122 | - |
| prefix_144 | A1 | True | 174 | 144 | 0 | 30 | 30 | 12 | 10212.3812 | 1.5729 | 14138 | 0.0005 |
| prefix_144 | A2 | True | 174 | 144 | 0 | 30 | 30 | 12 | 10212.3812 | 1.5729 | 14138 | 0.0005 |
| prefix_512 | A0 | True | 514 | 512 | 2 | 0 | 2 | 1 | 8816.3474 | 3.1270 | 50383 | - |
| prefix_512 | A1 | True | 649 | 512 | 0 | 137 | 137 | 47 | 8816.4419 | 3.8838 | 50621 | 0.0946 |
| prefix_512 | A2 | True | 649 | 512 | 0 | 137 | 137 | 47 | 8816.4419 | 3.8838 | 50621 | 0.0946 |
| scale_2x | A0 | True | 146150 | 87206 | 58944 | 0 | - | - | 337.8427 | 54.6664 | 11388415 | - |
| scale_2x | A1 | True | 174989 | 87206 | 30255 | 57528 | - | - | 345.6065 | 66.5259 | 11344482 | 7.7638 |
| scale_2x | A2 | True | 176081 | 87206 | 53490 | 35385 | - | - | 342.7799 | 58.7790 | 11407989 | 4.9372 |

## Observed decision

No deterministic pressure arm is promoted: every measured A1/A2 case increases both mean TTH and source wait relative to A0.
At 144 and 512 segments A1 and A2 collapse to exactly the same source counters, distinct HOLD states and business metrics.

## Interpretation boundary

The local/downstream HOLD counters count admission attempts, including retries. A distinct observed HOLD state deduplicates evidence intervals by source generation, selected bag and blocker state. Neither quantity is a bag routing mutation: HOLD only defers admission. Raw source-wait intervals are discarded after compact counting.

The optional 1x/2x capacity cases disable interval telemetry and retain only counters, business metrics and safety gates. Positive TTH, source-wait and event deltas mean the treatment is worse than A0.

This is fixed-map research evidence, not production promotion authority.
