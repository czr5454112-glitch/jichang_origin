# G4IRSF22 final decision and next step

## Decision

Status: `CURRENT_ROUTE_256_HSYSTEM64_COMPLETE_NO_RUNTIME_AUTHORIZATION`.

G22 does **not** authorize a new Route guidance rule, model, planner, or
supervisor. The production candidate remains `A0 + S4 + J2 + E2` with the
existing one-hop shield, reservation depth one, JIT merge service, bounded
recovery, and exact S4 fallback.

This is a system-externality veto, not a claim that local information or every
earlier intervention is useless. The 256-group current-point campaign found 22
actions that helped their directly affected bag. In the 64-group H_system veto
panel, however, only 5 of those 22 also improved the 57,012-bag mean, 16 made it
worse, and 1 was system-neutral. Only one direct-positive action improved the
mean without regressing p95 or p99, and its system gain was only
`0.003310 s/raw bag`. That is not a deployable selector.

No deterministic residual, linear model, tiny MLP, new runtime mutation, or
4x campaign is justified by this evidence. The next bounded experiment moves
to the existing Source ADMIT/HOLD seam at the measured storage-out hotspot.

## What was implemented

- One controlled `G22_S4_J2_E2` research profile with a formal 2x shape gate:
  57,012 raw bags and 87,206 runtime segments. G15 and G20 retain their original
  1x contracts.
- A rich Route census preserving event, runtime-bag, task, segment, owner,
  legal actions, and the existing local candidate observations.
- Complete action targets containing every legal alternate edge plus native
  WAIT, with separate H_bag and H_system compaction.
- A branch-local 5/15/30/60-second scalar accumulator for queue area, scheduled
  incoming area, next-service deficit, and queued wait. It is offline-only.
  Service-completion count is explicitly unavailable rather than inferred from
  expired or cancelled reservations.
- A matched same-origin S4/v2-safe gap ledger and Route-decision-sampled
  congestion episode detector.

No second event loop, full-route planner, central MAPF solver, global queue or
reservation scan, online future oracle, new seal/hash family, or learned
runtime component was added.

## Matched 2x coordination gap

The same 57,012 tasks and 87,206 segments were run once under S4/J2/E2 and once
under the offline v2-safe comparator.

| S4 minus v2-safe | Seconds/raw bag |
| --- | ---: |
| Total | 90.458043 |
| Source wait | 54.666355 |
| Inclusive Route wait | 43.138709 |
| Arithmetic residual | -7.347022 |
| Network diagnostic | 35.791688 |

The residual is only the arithmetic remainder after measured Source and Route
wait. It includes motion, service, and uninstrumented coordination; it is not
claimed as a pure coordination causal effect. Merge wait is a diagnostic
subset of inclusive Route wait and is never added twice.

The segment-weighted leg diagnostic is:

| Leg | Segments | Total delta | Source delta | Route-wait delta |
| --- | ---: | ---: | ---: | ---: |
| direct | 26,818 | 2.698107 | 6.004820 | 2.720604 |
| storage_in | 30,194 | 93.723315 | 8.681741 | 88.947820 |
| storage_out | 30,194 | 74.682200 | 89.205289 | -9.910165 |

These rows do not use the raw-bag denominator of the additive bank. The
storage-out Source seam is `node_52`, not the original task sources
`node_53/1/2/0`. Its largest measured cells are:

| Leg/source/block | Segments | Total delta | Source delta | Route-wait delta |
| --- | ---: | ---: | ---: | ---: |
| storage_out / node_52 / 7 | 3,600 | 500.838136 | 583.655486 | -62.663073 |
| storage_out / node_52 / 8 | 1,216 | 200.026021 | 200.836349 | -0.352130 |

This is why the next experiment targets Source timing rather than another
generic Route model.

## Congestion detection coverage

The rich census contains 464,849 multi-action Route rows. A fixed 16/8
enter/exit hysteresis found 339 sampled episodes; all 339 closed and cover 12
owners, 19 time blocks, and direct/storage_in/storage_out legs.

The signal is candidate-consistent current junction queue/contention, capped at
32 in this census. These episodes are descriptive Route-decision samples, not
independent causal units or continuous physical queue telemetry.
`affected_row_count` counts decisions, not unique bags, and sampled closure
does not prove continuous physical emptying. The coverage is sufficient for
detection, so G22 adds no heap scan or telemetry supervisor.

## Current-point exact action campaign

The selector attempted 256 unique runtime bags: 128 supported high-target-queue
states and 128 supported high-merge-contention states. Calendar-wait and
S4/v2-divergence strata had no score above the explicit `1e-9` support
threshold, so they are reported as unsupported rather than fabricated.

All 256 groups were sent to the exact seam. Ninety groups were dropped as whole
groups because at least one requested action was a native screening false
positive. The remaining 166 groups contain the full three-action contract:
S4, the other legal edge, and WAIT.

| Action evidence | Groups/actions | Beneficial | Harmful | Neutral | Mean direct affected-bag gain vs S4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Complete groups | 166 | — | — | — | — |
| All non-S4 treatments | 332 | 22 | 215 | 95 | -23.758886 s |
| Alternate edge | 166 | 20 | 146 | 0 | -45.014759 s |
| WAIT | 166 | 2 | 69 | 95 | -2.503012 s |

The 22 direct positives span 7 owners and 9 time blocks, so the H_bag signal is
real. These are treatment-level observations, however; edge and WAIT in one
group share a baseline and are not independent policy trials.

## H_system safety-veto panel

The panel deliberately contains all 22 H_bag-positive groups, 21 severe-harm
groups, and 21 near-boundary groups. It is outcome-informed safety evidence,
not a held-out training or policy-evaluation sample.

Four process-isolated shards completed all 256 requested pairs: 128 H_bag and
128 H_system. Every pair was same-state, action-changing, horizon-complete, and
passed the live/hard gates; all 128 H_system rows were formally evaluated and
passed. Every H_system row uses 57,012 raw bags; there were no group failures.

H_system values below are `treatment minus baseline`, so negative is better.

| H_system treatments | Count | Mean beneficial | Mean harmful | Mean neutral | Mean treatment-minus-baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| All panel actions | 128 | 15 | 83 | 30 | +1.225252 s/raw bag |
| H_bag-positive actions | 22 | 5 | 16 | 1 | +2.951204 s/raw bag |
| H_bag-harmful actions | 78 | 10 | 64 | 4 | +1.175880 s/raw bag |

Seven actions had a negative mean with no p95/p99 regression, but four were
smaller than `0.001 s/raw bag`. The three material rows expose two different
mechanisms:

| Event/action | Direct bag gain | System mean delta | p95 delta | p99 delta | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| 2084094 / edge 21 | -257.100 s | -1.812684 | -23.3100 | -7.8895 | Sacrifices one bag, relieves the cohort |
| 1268733 / edge 21 | -437.800 s | -1.189311 | -26.0725 | 0.0000 | Sacrifices one bag, network relief exceeds Source cost |
| 5296831 / edge 26 | +43.500 s | -0.003310 | 0.0000 | 0.0000 | Only direct-positive mean-and-tail-safe row |

The two cohort-relief rows are a verified new hypothesis: a system objective
can prefer an action that is bad for the acting bag. They do not authorize a
runtime rule because the panel is outcome-selected, there is no held-out local
selector, and the individual-delay/fairness contract has not been defined.

Large direct gains were generally transferred downstream. For example,
direct gains of `+1,189.25 s` and `+822.70 s` caused system mean regressions of
`+13.931651` and `+10.996134 s/raw bag`; their p95 regressions were `83.79` and
`74.99 s`. Two other mean-beneficial direct actions regressed p99. This is the
decisive reason not to deploy current Route guidance.

## Fixed local-information heuristic screen

The branch-local summaries are exact observations, but their fixed cost
formula is only a heuristic screen. It is not a perfect-information upper
bound, has no held-out fit, and does not prove that local information is
intrinsically worthless.

| Horizon | Non-S4 selections | Beneficial | Harmful | Beneficial precision | Mean gain vs S4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5 s | 121 | 7 | 64 | 0.0579 | -6.887349 s |
| 15 s | 124 | 8 | 68 | 0.0645 | -1.963855 s |
| 30 s | 123 | 8 | 67 | 0.0650 | -1.957831 s |
| 60 s | 122 | 8 | 65 | 0.0656 | -1.948193 s |

The three-of-four consensus chose 123 non-S4 actions across 166 groups: 8 were
beneficial, 67 harmful, and the mean gain was `-1.957831 s`. No horizon had a
positive mean. The outcome-only perfect-action ceiling is
`+62.504819 s/group`, which proves action freedom exists but is never an input
to the heuristic. G22 therefore stops before fitting a deterministic residual,
linear model, or MLP.

## Precursor, Merge, and Source interpretation

The earlier exploratory precursor run found only three valid same-runtime-bag
predecessors and completed two groups. That is a bounded observation, not a
256-group precursor no-go and not evidence for a universal one-step ceiling.
It is not used to authorize or reject a precursor model.

G22 does not reopen Merge ownership: J2 is already the verified simple JIT
mechanism, and the matched ledger cannot assign a comparable v2 merge-grant
delta. More importantly, the measured gap points directly to Source. Expanding
another Route/precursor campaign before testing that seam would add cost and
complexity without following the strongest evidence.

The next smallest experiment is therefore:

1. Reuse the existing Source opportunity/checkpoint seam.
2. Restrict to `storage_out`, `node_52`, release block 7; use block 8 as the
   confirmation cell.
3. Compare only ADMIT-current-front with HOLD-one-natural-opportunity.
4. Continue unchanged with S4/J2/E2 and evaluate H_bag first, then the full
   H_system mean and p95/p99.
5. Add no top-K reorder, supervisor, future route, global queue, or eager token
   reservation.

This is a targeted falsification test. G16's broad Source policy remains
rejected.

## Closed-loop and scale consequences

- Guidance candidates: none authorized.
- Native guidance mutations: none added.
- New candidate 1x/2x business runs: not triggered; the verified baseline
  remains `A0 + S4 + J2 + E2`.
- Measured gap closure by a new G22 policy: `0%`, because no unsafe candidate is
  promoted merely to create a performance number.
- 4x/full parallel/fault campaign: not triggered without a Direction pass.
  Existing process-isolated rollout support and fault lease recovery are left
  unchanged.
- Final label: `CURRENT_ROUTE_SYSTEM_EXTERNALITY_VETO`, not
  `ONE_STEP_LOCAL_INFORMATION_CEILING`.

## Reproducibility and complexity boundary

The runners reproduce the large artifacts when needed. The 1.07 GB Route
census, 216 MB matched raw cache, raw exact pair payloads, and per-row
task/segment ledgers are intentionally excluded from Git. The repository keeps
the code, tests, compact action groups, four H_system summaries, gap tables,
episode descriptors, decision summary, and evidence-bound idea log.

This preserves the project's direction: one-hop decentralized decisions with
MAPF-inspired local contention signals and bounded fallback, while refusing to
reintroduce centralized full-route planning or an unverified learned layer.
