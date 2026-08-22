# G4IRSF25 real corridor trajectories

- Status: `MEASURED`.
- Compact raw rows: `build/g4irsf25_clcr_campaign/corridor_trajectories.jsonl` (build evidence; identity is trace-only).
- Registered branches/arms: 4 / 8.
- Real trajectories / completed rejoin / timeout / censored / loop / unsafe: 48516 / 25778 / 204 / 22534 / 0 / 0.
- Absolute time and bag/task/segment identity are excluded from every exported policy artifact.

| scale | branch | edge | rejoin | trajectories | completed | timeout | censored | paths | redecisions |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1x | 6 | 8 | 13 | 1367 | 1 | 0 | 1366 | 2 | 8198 |
| 1x | 6 | 12 | 13 | 1833 | 1833 | 0 | 0 | 1 | 1833 |
| 1x | 9 | 7 | 14 | 3199 | 1515 | 0 | 1684 | 3 | 19117 |
| 1x | 9 | 10 | 14 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1x | 16 | 17 | 24 | 4887 | 4702 | 0 | 185 | 2 | 16141 |
| 1x | 16 | 21 | 24 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1x | 19 | 18 | 26 | 4886 | 146 | 0 | 4740 | 4 | 31832 |
| 1x | 19 | 25 | 26 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2x | 6 | 8 | 13 | 2671 | 92 | 32 | 2547 | 9 | 15713 |
| 2x | 6 | 12 | 13 | 3729 | 3712 | 17 | 0 | 2 | 3712 |
| 2x | 9 | 7 | 14 | 5241 | 2663 | 122 | 2456 | 10 | 29030 |
| 2x | 9 | 10 | 14 | 1157 | 1157 | 0 | 0 | 1 | 2314 |
| 2x | 16 | 17 | 24 | 8735 | 7647 | 31 | 1057 | 8 | 34859 |
| 2x | 16 | 21 | 24 | 1039 | 1039 | 0 | 0 | 1 | 2078 |
| 2x | 19 | 18 | 26 | 9691 | 1190 | 2 | 8499 | 5 | 55884 |
| 2x | 19 | 25 | 26 | 81 | 81 | 0 | 0 | 1 | 81 |

A zero row means the registered arm was genuinely not selected in a measured observe run; an absent/unrun scale is `NOT_MEASURED`, not a zero-support claim.
