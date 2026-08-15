# G4IRSF24 New Ideas

These are bounded follow-ups exposed by measured G24 results. They do not add a second framework.

1. **Keep S4 as the deployment baseline.** It already beats fresh centralized HCA on processed mean by `10.959%`; any DLP candidate must beat S4, not merely HCA.
2. **Keep the corridor pivot as no-go evidence.** Strongest supplied corridor margin is `0.500` s with status `MEASURED_NO_GO`. Its mixed 1×/2× result does not activate DLP; at most test one existing local congestion threshold, then stop if 1× still regresses.
3. **Treat release alignment as protocol, not bookkeeping.** Exact release minus canonical pass reaches `1213.000` seconds, so future 1x comparisons must reuse `artifacts/datasets/g4irsf24_release_compact.csv`.
4. **Use real mutations as the learning gate.** Zero-mutation or unsafe DLP candidates stop after screening; no extra selector layer is warranted.
5. **Separate business time from computation time.** Add one parent-observed end-to-end timer before claiming a Java/native runtime speedup; keep core wall as a diagnostic.

Current DLP/scale status: `NO_EXTEND`. Missing experiments remain `NOT_MEASURED`.
