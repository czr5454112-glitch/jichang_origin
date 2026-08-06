# G4IRSF17 final joint decision

Decision: **`TERMINAL_WITH_CAPACITY_CENSORING_ACTIONABLE_PIVOT`**.

The amended workflow is terminal, but the original 4x fault matrix is capacity-censored and fault advantage is not estimable. A--E promotion/no-go classification is deferred; the next bounded pivot remains actionable.

Next pivot: **strictly-local just-in-time service-slot arbitration over a bounded pending set**.

## Verified Phase-A result

At 8,192, the matched Phase-A run covered **4898 raw bags**: H5−off source wait was **+0.149551 s/bag**, network time **-0.058518 s/bag**, and total TTH **+0.091033 s/bag**. The **732.500 s** positive additional source wait was **100.00% downstream backpressure**, which verifies the bounded I1 pilot + G2 pivot; it does not authorize G2. Attribution remains at the native aggregate-interval granularity; no per-bag blocker identity is inferred from aggregate rows.

## Evidence gates

| Evidence gate | Status |
|---|---|
| Phase-A source-wait attribution | COMPLETE |
| I1 causal/model evidence | TRAINED_NOT_AUTHORIZED |
| G2 M1–M6 matched action screen | CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT |
| G2 causal authorization | FALSE / NOT AUTHORIZED |
| 144→43,603 matched ladder | BASELINE_ONLY_NO_AUTHORIZED_CANDIDATE |
| Native 1×/4× fault matrix | TERMINAL_WITH_CAPACITY_CENSORING |
| Fixed-map 1×–16× scale matrix | COMPLETE |

A missing experiment is neither a zero effect nor a pass. Levels A–E are assigned only after all three system tracks are complete.
