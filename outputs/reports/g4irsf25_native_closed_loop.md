# G4IRSF25 native closed loop

This report is derived only from G25 native campaign run rows. HCA and G24 static-corridor results are not inferred here.
A 1x/2x value is measured only when repeat 0 and repeat 1 both contain complete timing populations; negative deltas are faster than S4.

| policy | scale | balanced evidence | mean s | p95 s | p99 s | max s | mean ΔS4 s | p95 ΔS4 s | p99 ΔS4 s | max ΔS4 s | mutations | safety |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| S4 | 1x | `MEASURED_BALANCED_REPEATS` | 210.770 | 247.204 | 254.004 | 407.404 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | `PASS` |
| S4 | 2x | `MEASURED_BALANCED_REPEATS` | 283.176 | 512.004 | 1284.029 | 5511.454 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | `PASS` |
| T0 | 1x | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` |
| T0 | 2x | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` |
| L1 | 1x | `MEASURED_BALANCED_REPEATS` | 216.691 | 272.602 | 275.404 | 295.454 | 5.921 | 25.398 | 21.400 | -111.950 | 13086 | `PASS` |
| L1 | 2x | `MEASURED_BALANCED_REPEATS` | 275.627 | 463.203 | 1076.648 | 5369.604 | -7.549 | -48.801 | -207.381 | -141.850 | 31776 | `PASS` |
| L2 | 1x | `MEASURED_BALANCED_REPEATS` | 215.486 | 261.604 | 275.004 | 298.652 | 4.716 | 14.400 | 21.000 | -108.752 | 19418 | `PASS` |
| L2 | 2x | `MEASURED_BALANCED_REPEATS` | 284.998 | 497.048 | 1261.333 | 5877.004 | 1.821 | -14.956 | -22.696 | 365.550 | 32892 | `PASS` |
| L3 | 1x | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` |
| L3 | 2x | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` | NOT_MEASURED | `NOT_MEASURED` |

## Native prefix screens

| policy | 144 | 512 | 8192 |
|---|---|---|---|
| S4 | PASS; mutations=0 | PASS; mutations=0 | PASS; mutations=0 |
| T0 | PASS; mutations=0 | PASS; mutations=0 | PASS; mutations=0 |
| L1 | PASS; mutations=22 | PASS; mutations=71 | PASS; mutations=1202 |
| L2 | PASS; mutations=28 | PASS; mutations=86 | PASS; mutations=1548 |
| L3 | `NOT_MEASURED` | `NOT_MEASURED` | `NOT_MEASURED` |

Incomplete or absent populations remain literal `NOT_MEASURED`; they are never converted to zero benefit, zero mutation, or a tail statistic.
