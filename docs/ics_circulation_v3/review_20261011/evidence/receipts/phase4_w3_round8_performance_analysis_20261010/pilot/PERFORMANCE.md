# Round8 terminal-screen paired performance

pilot: 3 business cases, 2 blocks, 6 on/off pairs, 12 independent physical episodes. All exact: True. All predeclared cases and timing regressions retained.

## Complete paired timing totals

| Metric (seconds) | Off | On | On − off | Off/on | Lower / equal / higher pairs |
|---|---:|---:|---:|---:|---:|
| algorithm_cpu_seconds | 3.250000 | 2.718750 | -0.531250 | 1.1954 | 4/1/1 |
| algorithm_wall_seconds | 3.301345 | 2.845311 | -0.456035 | 1.1603 | 5/0/1 |
| search_cpu_seconds | 3.218750 | 2.687500 | -0.531250 | 1.1977 | 5/0/1 |
| screen_cpu_seconds | 0.000000 | 0.031250 | 0.031250 | 0.0000 | 0/4/2 |
| observer_cpu_seconds | 14.593750 | 14.078125 | -0.515625 | 1.0366 | 4/0/2 |
| whole_simulation_cpu_seconds | 165.078125 | 160.593750 | -4.484375 | 1.0279 | 4/0/2 |
| whole_simulation_wall_seconds | 166.392078 | 162.131884 | -4.260194 | 1.0263 | 4/0/2 |
| process_cpu_seconds | 194.046875 | 189.250000 | -4.796875 | 1.0253 | 3/0/3 |
| launch_to_exit_wall_seconds | 196.426613 | 191.792006 | -4.634607 | 1.0242 | 3/0/3 |

These totals are nested measurement axes, not additive resource cost. Launch elapsed totals are descriptive per-invocation sums, never global elapsed time.

Search work 367642 → 331642; extra screen work 17456; queries 578 in each arm. Screen record work is not the same unit as search expansion work.

## Every business case (mean of both blocks)

| Case | Algorithm off CPU | Algorithm on CPU | CPU delta | Whole-simulation CPU delta | Full-process CPU delta |
|---|---:|---:|---:|---:|---:|
| counterflow__nominal__same_zone32plus32 | 0.789062 | 0.828125 | 0.039062 | -1.789062 | -1.859375 |
| cross_cycle__nominal__same_zone32plus32 | 0.320312 | 0.226562 | -0.093750 | -1.429688 | -1.476562 |
| near_full__nominal__same_zone32plus32 | 0.515625 | 0.304688 | -0.210938 | 0.976562 | 0.937500 |

Each block and its exact arm order and all deltas are in analysis.json. The same JSON records startup/import boundaries and single-worker lifetime peak memory.

- Two timing repeats do not create new business samples. All cases and both orders retained.
- Algorithm CPU includes validity/dispatch/screen/search; excludes common observer. Whole simulation includes identical instrumentation.
- Observer work varies naturally with private cache contents even under identical observation code. Per-query timer resolution may produce measured zeros.
- Elapsed times measured with up to three performance children and independent main-line workers; not unloaded production latency or hard realtime.
- Search work and screen record work are different units. Private cache history may change; candidate and physical equality are checked separately.

Analysis: 65 checks, 0 failures; CPU 0.046875s, wall 0.036011s through calculation, excluding final output writes.
