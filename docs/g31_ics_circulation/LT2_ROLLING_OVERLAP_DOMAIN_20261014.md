# New finite overlap domain: preregistration and limits

This is a separate synthetic mechanism diagnostic. The prior online rolling
campaign had already completed E before L's first return at gates 6 and 12,
so no later shared-resource competition remained. The new domain changes two
public exogenous contracts while preserving the graph, two trays, four jobs,
FIFO, capacities, headways and physical service rules within every comparison.

Receiver load lasts 3, 5 or 7 seconds: the old public 3-second duration plus
zero, one or two public 2-second return-edge travel times. Storage gates are
0 and 5.4 seconds. The latter is the maximum of the two initial path service
and travel bounds, calculated from the initial load end at 0.1 seconds. It
masks the initial detour's extra travel without selecting a gate from observed
outcomes. Gate 0 remains as the negative control where that extra travel can
violate strict protection.

Each of six cases contains all sixteen actions: initial next node 1 or 2,
E supply at 0.11 or 2.21 seconds, first L return immediately or after one
0.5-second shared-edge headway, and first reuse suffix via 3 or 8. The second
return is immediate and the second reuse uses suffix 3 in every arm. All 96
projections, including incomplete and protection-failing cells, are retained.
The incumbent is route 1, supply at 2.21, immediate return, later route 3.

Strict coordinate moves, plateau coordinate moves, resource-pair destroy/repair
and full finite-horizon enumeration receive the same public initial model,
actions, per-job protection rule and sixteen-evaluation budget. Pair repair
is an explicit limited adaptation, not a reproduction or novel extension of
LNS. Enumeration is a finite model reference, not continuous optimization or
actual rolling MPC. Every method retains unexecuted candidates as unknown.

The primary structural test is the full initial-R1 / return-R2 / later-R1
cube at each fixed supply time. Per-job and total third differences diagnose
nonadditivity only when all eight projections finish. A selected later-route
action is also compared with the otherwise identical route-3 continuation.
Protection remains exactly zero tolerance. A separate numerical display flag
at 1e-9 only distinguishes interaction magnitudes from floating-point noise;
it never changes protection.

The public model is approximate and its new duration cases have no native
validation. This package does not authenticate message delivery or certify
permissions, ACKs, edges, physical gains or a rolling method. Native execution
would need a versioned supported-input adapter, real fresh decisions from
owner-local delivered facts, matched protocol traffic and an all-job physical
comparison. There is no permission to infer current remote state from this
offline table. No original-map input or old study is changed.

The first pure campaign completed all 96 projections in 0.608 seconds, with
unchanged source hashes and zero native calls. Evidence is in
`outputs/experiments/g31_ics_lt2_sustained_20261014/rolling_overlap_domain_001/`.
All failures of the strict modeled protection rule remain in the denominator.
Fourteen focused pure tests passed in `rolling_overlap_pure_tests_002.xml`.

| Storage gate | Receiver load | Strict coordinate gain | Plateau / pair / enumeration gain | Strong-reference later suffix |
| --- | --- | --- | --- | --- |
| 0 | 3 | 0 | 0 | 3 |
| 0 | 5 | 2.14 | 2.14 | 8 |
| 0 | 7 | 0 | 0 | 3 |
| 5.4 | 3 | 0 | 1.41 | 3 |
| 5.4 | 5 | 0.14 | 2.23 | 3 |
| 5.4 | 7 | 0.11 | 2.20 | 3 |

These are projected sums of completion-time improvements, not native business
gains. Plateau coordinate search matched pair repair and complete enumeration
in every case. At gate 0 / load 5, the useful later bypass is found by ordinary
strict coordinate search. At gate 5.4, all strong solutions use initial route 2
and early E supply, but retain later suffix 3. The third-order mixed differences
are nonzero only in the unmasked gate-0 cubes at loads 5 and 7; those cubes also
contain initial-detour protection failures. Neither nonadditivity nor a weak
baseline's failure establishes a joint-method advantage.

This negative result identifies a structural limitation of this fixture. The
gate that protects the longer initial detour also equalizes the loaded release
time. Meanwhile, earlier E service can remove the later conflict entirely.
A new mechanism would need initial routing to improve actual release under
real pre-existing occupancy, without relying on that equalizing gate. The
current campaign is not extended with outcome-chosen timings or native runs.
