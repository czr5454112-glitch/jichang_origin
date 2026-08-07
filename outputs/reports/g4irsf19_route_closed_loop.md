# G4IRSF19 Route closed loop

The selected Route closed loop is J2 merge timing plus the existing S4
queue/calendar-aware one-hop scorer.

| Load | Mean TTH S1 -> S4 | P95 S1 -> S4 | P99 S1 -> S4 | Source wait S1 -> S4 | Safety |
|---:|---:|---:|---:|---:|:---:|
| 1x | 214.945 -> 213.912 s | 257.804 -> 252.004 s | 295.994 -> 281.004 s | 0.078 -> 0.050 s | pass |
| 2x | 851.864 -> 337.843 s | 4,669.424 -> 960.004 s | 7,386.187 -> 2,242.954 s | 502.462 -> 54.666 s | pass |

Both runs completed every requested bag, reported zero loops, and passed all
hard safety gates. S4 also reduced mean route wait at 2x from 140.379 s to
72.768 s and merge-grant wait from 6.989 s to 4.950 s.

The compact paired table is `outputs/tables/g4irsf19_route_full_scale.csv`.
