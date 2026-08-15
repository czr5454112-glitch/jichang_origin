# G4IRSF24 Causal Explanation

Status: `MEASURED_LIMITED`.

- The exact-release fresh race establishes the arm-level S4 business effect, but it does not attribute that effect to an individual local feature.
- The selected generic EWMA/TD screen arms produced 0 proposals and 0 committed mutations across 144/512. Offline lookup/Bellman coverage and held-out errors are reported separately; coverage alone is not treated as a win.
- The reconvergent projection changed 1834 actions at 1× and 8897 at 2×. Its strongest setting had mean/p95/p99 deltas of 0.227/0.000/0.800 seconds at 1× and -4.855/-16.328/-159.361 seconds at 2× (negative is faster), showing a load-dependent effect rather than a deployable general win.
- No 64–128-action H_system intervention or dedicated injected-fault campaign was run because no learning candidate passed the registered 1×/2× gate.
