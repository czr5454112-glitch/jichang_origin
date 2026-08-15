# G4IRSF24 New Ideas

These are bounded follow-ups exposed by measured G24 results. They do not add a second framework.

1. **Keep S4 as the deployment baseline.** It already beats fresh centralized HCA on processed mean by `10.959%`; any DLP candidate must beat S4, not merely HCA.
2. **Keep the corridor pivot as no-go evidence.** Strongest supplied corridor margin is `0.500` s with status `MEASURED_NO_GO`. Its mixed 1×/2× result does not activate DLP; at most test one existing local congestion threshold, then stop if 1× still regresses.
3. **Treat release alignment as protocol, not bookkeeping.** Exact release minus canonical pass reaches `1213.000` seconds, so future 1x comparisons must reuse `artifacts/datasets/g4irsf24_release_compact.csv`.
4. **Use real mutations as the learning gate.** Zero-mutation or unsafe DLP candidates stop after screening; no extra selector layer is warranted.
5. **Separate business time from computation time.** Add one parent-observed end-to-end timer before claiming a Java/native runtime speedup; keep core wall as a diagnostic.

Current DLP/scale status: `NO_EXTEND`. Missing experiments remain `NOT_MEASURED`.

## G4IRSF25 parallel execution boundary

The smallest safe parallel change is to let **independent runtime instances**
overlap during their pure C++ event loops. Two complete exact-release S4 runs
in a two-thread pool preserved all bag outputs and strict safety projections.
The final balanced two-round probe improved aggregate throughput by `1.701x`,
only `0.001x` above its gate, while median single-run wall time regressed by
`12.2%`, above the registered
`10%` latency guard. This is therefore `GO_BATCH_THROUGHPUT_ONLY`, not a live
single-stream default; remeasure locally before using even the batch option.

Do not build one mutable actor per junction from the current evidence. The
canonical 512-segment prefix had event width/fraction `1.094/0.166` and
decision width/fraction `1.087/0.157`. A second deterministic densest-release
512 window raised the observed event values to `1.645/0.634`, but its complete
decision values were only `1.610/0.623`, still below the required width `1.70`.
The registered result is therefore `NO_GO_ON_TESTED_512_WINDOWS`, not a
universal no-go for larger maps or new workloads. J2, corridor calendars, and
bounded PIBT also cross node ownership boundaries.

Only revisit same-stream parallelism on a larger topology or workload if a new
trace first passes both gates. The next implementation, if unlocked, should
parallelize immutable one-step proposals and retain deterministic serial
validation/commit in `(time, microphase, seq)` order. It should not introduce a
general actor framework, locks around the whole runtime, or another policy
layer.
