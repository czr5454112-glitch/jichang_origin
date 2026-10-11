# Round8 terminal-screen paired performance

formal: 27 business cases, 2 blocks, 54 on/off pairs, 108 independent physical episodes. All exact: True. All predeclared cases and timing regressions retained.

## Complete paired timing totals

| Metric (seconds) | Off | On | On − off | Off/on | Lower / equal / higher pairs |
|---|---:|---:|---:|---:|---:|
| algorithm_cpu_seconds | 32.093750 | 24.687500 | -7.406250 | 1.3000 | 37/3/14 |
| algorithm_wall_seconds | 32.060377 | 24.480881 | -7.579497 | 1.3096 | 34/0/20 |
| search_cpu_seconds | 32.062500 | 24.093750 | -7.968750 | 1.3307 | 38/3/13 |
| screen_cpu_seconds | 0.000000 | 0.531250 | 0.531250 | 0.0000 | 0/34/20 |
| observer_cpu_seconds | 116.578125 | 114.703125 | -1.875000 | 1.0163 | 35/4/15 |
| whole_simulation_cpu_seconds | 1357.406250 | 1348.015625 | -9.390625 | 1.0070 | 36/2/16 |
| whole_simulation_wall_seconds | 1366.714476 | 1357.361760 | -9.352716 | 1.0069 | 38/0/16 |
| process_cpu_seconds | 1588.250000 | 1579.500000 | -8.750000 | 1.0055 | 37/0/17 |
| launch_to_exit_wall_seconds | 1602.131520 | 1593.050058 | -9.081462 | 1.0057 | 37/0/17 |

These totals are nested measurement axes, not additive resource cost. Launch elapsed totals are descriptive per-invocation sums, never global elapsed time.

Search work 3332772 → 2774772; extra screen work 146930; queries 4934 in each arm. Screen record work is not the same unit as search expansion work.

## Every business case (mean of both blocks)

| Case | Algorithm off CPU | Algorithm on CPU | CPU delta | Whole-simulation CPU delta | Full-process CPU delta |
|---|---:|---:|---:|---:|---:|
| counterflow__error00__same_zone32plus32 | 0.937500 | 0.882812 | -0.054688 | 0.242188 | 0.367188 |
| counterflow__error01__same_zone32plus32 | 0.773438 | 0.906250 | 0.132812 | 0.023438 | 0.117188 |
| counterflow__error02__same_zone32plus32 | 1.320312 | 0.687500 | -0.632812 | -0.640625 | -0.625000 |
| counterflow__error03__same_zone32plus32 | 1.031250 | 0.937500 | -0.093750 | 0.664062 | 0.742188 |
| counterflow__error04__same_zone32plus32 | 0.273438 | 0.273438 | 0.000000 | -0.265625 | -0.398438 |
| counterflow__error05__same_zone32plus32 | 0.828125 | 0.960938 | 0.132812 | 0.289062 | 0.335938 |
| counterflow__error06__same_zone32plus32 | 2.109375 | 0.757812 | -1.351562 | -1.187500 | -1.335938 |
| counterflow__error07__same_zone32plus32 | 0.796875 | 0.867188 | 0.070312 | 0.218750 | 0.351562 |
| counterflow__nominal__same_zone32plus32 | 0.843750 | 0.929688 | 0.085938 | -0.664062 | -0.640625 |
| cross_cycle__error00__same_zone32plus32 | 0.312500 | 0.203125 | -0.109375 | 0.195312 | 0.203125 |
| cross_cycle__error01__same_zone32plus32 | 0.195312 | 0.210938 | 0.015625 | 0.351562 | 0.421875 |
| cross_cycle__error02__same_zone32plus32 | 0.218750 | 0.226562 | 0.007812 | -0.320312 | -0.429688 |
| cross_cycle__error03__same_zone32plus32 | 0.242188 | 0.304688 | 0.062500 | -0.312500 | -0.234375 |
| cross_cycle__error04__same_zone32plus32 | 0.367188 | 0.406250 | 0.039062 | 0.429688 | 0.578125 |
| cross_cycle__error05__same_zone32plus32 | 0.312500 | 0.281250 | -0.031250 | -0.070312 | -0.023438 |
| cross_cycle__error06__same_zone32plus32 | 0.406250 | 0.398438 | -0.007812 | -0.023438 | -0.039062 |
| cross_cycle__error07__same_zone32plus32 | 0.406250 | 0.343750 | -0.062500 | -0.117188 | -0.187500 |
| cross_cycle__nominal__same_zone32plus32 | 0.312500 | 0.304688 | -0.007812 | 0.054688 | 0.117188 |
| near_full__error00__same_zone32plus32 | 0.398438 | 0.234375 | -0.164062 | -0.265625 | -0.335938 |
| near_full__error01__same_zone32plus32 | 0.507812 | 0.312500 | -0.195312 | -0.562500 | -0.593750 |
| near_full__error02__same_zone32plus32 | 0.421875 | 0.242188 | -0.179688 | -0.476562 | -0.351562 |
| near_full__error03__same_zone32plus32 | 0.484375 | 0.257812 | -0.226562 | -0.492188 | -0.492188 |
| near_full__error04__same_zone32plus32 | 0.406250 | 0.203125 | -0.203125 | -0.343750 | -0.375000 |
| near_full__error05__same_zone32plus32 | 0.515625 | 0.320312 | -0.195312 | -0.476562 | -0.453125 |
| near_full__error06__same_zone32plus32 | 0.554688 | 0.304688 | -0.250000 | -0.406250 | -0.500000 |
| near_full__error07__same_zone32plus32 | 0.515625 | 0.296875 | -0.218750 | -0.296875 | -0.335938 |
| near_full__nominal__same_zone32plus32 | 0.554688 | 0.289062 | -0.265625 | -0.242188 | -0.257812 |

Each block and its exact arm order and all deltas are in analysis.json. The same JSON records startup/import boundaries and single-worker lifetime peak memory.

- Two timing repeats do not create new business samples. All cases and both orders retained.
- Algorithm CPU includes validity/dispatch/screen/search; excludes common observer. Whole simulation includes identical instrumentation.
- Observer work varies naturally with private cache contents even under identical observation code. Query process_time intervals are quantized; zero is not absence of work or latency. Episode algorithm CPU is a sum of sampled intervals, not an exact fine-grained CPU attribution. Complete OS process lifetime is a separate stronger total measurement.
- Elapsed times measured with up to three performance children and independent main-line workers; not unloaded production latency or hard realtime.
- Search work and screen record work are different units. Private cache history may change; candidate and physical equality are checked separately.
- Cold means the explicitly exported private routing cache is empty at algorithm start. OS filesystem/page caches are neither flushed nor claimed cold; process isolation does not imply an unloaded or hardware-cache-isolated machine.

Analysis: 623 checks, 0 failures; CPU 26.406250s, wall 26.638616s through calculation, excluding final output writes.

Environment observed during formal execution: Python 3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)], Windows-10-10.0.26200-SP0, 16 physical / 22 logical CPU cores, 33736028160 bytes RAM. This snapshot is not a pre-run load or frequency guarantee. Performance children capped at three; concurrent main-line workers capped at six.

## CPU timer quantization

| Arm / query role / timer | Active intervals | CPU-zero count | CPU-zero fraction | Minimum positive CPU (ms) | Largest elapsed time with CPU zero (ms) |
|---|---:|---:|---:|---:|---:|
| off/empty/algorithm | 2050 | 1408 | 68.6829% | 15.625000 | 22.569700 |
| off/empty/observer | 2050 | 164 | 8.0000% | 15.625000 | 16.453400 |
| off/empty/screen | 0 | 0 | inactive | n/a | 0.000000 |
| off/empty/search | 2050 | 1408 | 68.6829% | 15.625000 | 22.555600 |
| off/loaded/algorithm | 2884 | 1820 | 63.1068% | 15.625000 | 16.201300 |
| off/loaded/observer | 2884 | 503 | 17.4411% | 15.625000 | 22.562300 |
| off/loaded/screen | 0 | 0 | inactive | n/a | 0.000000 |
| off/loaded/search | 2884 | 1822 | 63.1761% | 15.625000 | 16.187400 |
| on/empty/algorithm | 2050 | 1473 | 71.8537% | 15.625000 | 11.525400 |
| on/empty/observer | 2050 | 219 | 10.6829% | 15.625000 | 24.354800 |
| on/empty/screen | 2050 | 2033 | 99.1707% | 15.625000 | 0.394100 |
| on/empty/search | 1964 | 1406 | 71.5886% | 15.625000 | 11.393400 |
| on/loaded/algorithm | 2884 | 1908 | 66.1581% | 15.625000 | 13.633200 |
| on/loaded/observer | 2884 | 513 | 17.7878% | 15.625000 | 29.512500 |
| on/loaded/screen | 2884 | 2867 | 99.4105% | 15.625000 | 0.352500 |
| on/loaded/search | 2784 | 1826 | 65.5891% | 15.625000 | 13.402600 |

Disabled screen and skipped delegate intervals are counted as structurally inactive, separately from measured active zero CPU. JSON includes observed increment GCD and paired-difference minimum nonzero/GCD. These are observed quantization, not a claimed accuracy bound; elapsed measurements include concurrent load.

## Routing-cache history

Among 4934 corresponding queries, pre-query private-cache SHA differs in 130 and entry count differs in 20. Each episode starts with identical empty routing cache; skipped searches can change later warming and LRU history. This is part of the complete method trajectory, not a reason to force cache contents equal.

| Query role / decision / prior cache | Queries | Algorithm CPU delta (s) | Observer CPU delta (s) |
|---|---:|---:|---:|
| empty/certified/same_cache | 86 | -3.921875 | -0.078125 |
| empty/delegated/same_cache | 1964 | 0.421875 | -1.031250 |
| loaded/certified/different_cache | 82 | -3.234375 | -0.078125 |
| loaded/certified/same_cache | 18 | -0.703125 | 0.015625 |
| loaded/delegated/different_cache | 48 | 0.000000 | 0.093750 |
| loaded/delegated/same_cache | 2736 | 0.031250 | -0.796875 |

Every pair records first screen and first cache-divergence ordinals. Per-query deltas mix current screening, accumulated cache history, timer quantization and runtime variation; they are not clean causal net savings for the current certificate. Whole-episode on/off comparisons remain the primary experiment.

[Python process CPU and elapsed clock definitions](https://docs.python.org/3.11/library/time.html#time.process_time) distinguish CPU from elapsed time; integer nanoseconds avoid float representation loss. [Microsoft GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) defines cumulative per-process kernel/user CPU in 100 ns units. Neither representation unit establishes the empirical precision of each short sampled interval.
