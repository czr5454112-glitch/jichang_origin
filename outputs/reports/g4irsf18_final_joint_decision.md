# G4IRSF18 final joint decision

Decision: **`REAL_JIT_AND_RESEARCH_OWNERSHIP_PROVEN_PRODUCTION_NOT_PROMOTED`**.

G18 makes two material advances toward a decentralized, MAPF-inspired local
controller: destination merge decisions now occur at a real bounded-pending
service boundary, and a learned policy really owns and changes normal-flow
native actions. The deterministic JIT mechanism improves the fixed-map system
through 2x load. The learned J7 merge policy remains research-only because its
business effect is negligible, its full run adds a small amount of event work,
source and route ownership are still zero, and the 4x capacity boundary has not
been resolved.

Production closed-loop authorization and promotion remain false. This is an
actionable pivot, not a terminal no-go and not a claim that F2 has been replaced.

## What was implemented

- A strict per-destination bounded pending set. Requests register locally and
  compete only at the next natural service opportunity; overflow stays under
  local backpressure rather than reserving future slots.
- One coalesced merge wakeup per resource generation, lazy stale-event
  suppression, short exact leases, and fault/repair revalidation. No full A*,
  global reservation scan, future-route input, or future-schedule input was
  introduced.
- Three native controls: J0 eager, J1 JIT FIFO, and J2 JIT
  fair-aging-deadline with an authoritative 120-second starvation guard.
- A native 18D `MERGE_TRACE_LOCAL_V1` affine policy with shadow, fixed-workload
  research closed-loop, production fail-closed, explicit coverage and override
  caps, kill switch, OOD/invalid fallback, and separate proposal, ownership,
  mutation, and fallback counters.
- Resumable ladder, learned, scale, and fault campaigns with evidence-trace and
  capacity modes separated so retained trace rows cannot masquerade as
  controller cost.

## Direct answers required by the G18 plan

| Question | Evidence-backed answer |
|---|---|
| 1. Is GitHub CI green? | **Yes for predecessor PR #2.** Commit `ea65477` separates historical predecessor validation from the current successor runtime; GitHub Actions run 57 completed successfully. The historical evidence was not rehashed or rewritten. |
| 2. Did JIT create real decision opportunities? | **Yes.** At the 43,603 protected full rung J2 observed 3,621 multi-candidate service opportunities and changed 3,252 service orders. On the formal 1x/2x scale workloads it observed 4,722/40,226 multi-candidate opportunities and 3,465/31,257 mutations. These are native natural-service boundaries, not synthetic states or request-time proposals. |
| 3. How many normal-flow actions did the model change? | J7 changed **44** feature-distinct actions at 8,192 segments and **154** at the 43,603 full rung. The full run applied/owned 3,500 decisions from 3,526 eligible opportunities. |
| 4. What is ownership by head? | At 43,603: **Source 0, Route 0, Merge 3,500 ownership / 154 distinct mutations**. Merge ownership is 99.263% of the 3,526 eligible multi-candidate opportunities, but ownership that merely agrees with J2 is kept separate from mutation. |
| 5. What is the F2/J2 fallback rate and why? | For the learned merge head, **26/3,526 = 0.737%** of eligible full-run opportunities fell back to J2, entirely because of the starvation guard. Invalid artifact, OOD, authorization, kill-switch, tie, coverage, and override fallbacks were zero. System-wide F2 is still authoritative for source and route and is still the merge teacher/safety fallback, so an overall F2-replacement percentage must not be inferred from this merge-only denominator. |
| 6. Which input group was effective? | Only the directly observable **18D `MERGE_TRACE_LOCAL_V1`** group was evaluated end to end. The full 18D and all five group-removal variants tied at 0.962963 validation top-1 with the same regret, so no feature group is uniquely proven useful. F2-22D, G17-39D, RICH-60D, and legacy+rich-89D remain `NOT_EVALUATED` because the merge trace does not contain their complete native contracts; missing fields were not invented or zero-filled. |
| 7. Which learned model was genuinely effective? | **None is proven to deliver material business utility.** J3-J6 either copied FIFO or produced worse bounded-local choices. J7 is effective as a native-control seam: it generalizes the J2 teacher decision and produces real ownership/mutations. Its audit rollout had 25 harms, 0 benefits, and 2 neutral cases; closed-loop effects were neutral to tiny, so J7 remains a research candidate. The strongest proven performance policy is the non-learned J2 JIT rule at 2x. |
| 8. Did 1x full win? | **JIT won against eager; learned J7 did not earn promotion.** On the formal 1x scale stream, mean TTH was 217.467 s (J0), 214.905 s (J1), and 214.945 s (J2), with hard and algorithmic safety passing. In the separate protected 43,603 learned pair, J7 versus J2 changed mean TTH by -0.004653 s, left p95/p99 unchanged, had 207 improved / 286 harmed / 28,013 unchanged bags, and added 228 events. That is research evidence, not a production win. |
| 9. Did 2x improve? | **Yes, strongly.** J2 completed all 87,206 segments with mean TTH 851.864 s versus 959.393 s for J1 and 1,394.709 s for J0. The gain is dominated by source wait: 502.462 s versus 611.996/992.601 s. J2 used 89,518 more events than J1, so the improvement is real but not free. |
| 10. Is the 4x-16x limit physical capacity or an event storm? | **Not yet identifiable.** All three 4x arms reached the external 1,200-second wall boundary without a native return. CPU lower bounds were 1,199.844/1,154.875/1,151.969 s and RSS snapshots were 770.453/770.344/741.488 MiB. Completion, event counts, TTH, and algorithmic safety are unknown. Therefore 8x/16x full and 32x smoke were correctly blocked; the result is wall-censored, not an event-cap failure or proof of physical saturation. |
| 11. Is the learned policy the normal-flow primary controller? | **No.** It genuinely controls a high fraction of eligible merge decisions in fixed research workloads, but Source and Route ownership are zero, production gates are false, its distinct-action density is only 154/3,500, and its full business effect is negligible with slight event amplification. |
| 12. What is the narrowest valuable pivot? | **Move the next learning experiment to a local route/admission action at the verified 2x source-wait knee, using harm-sensitive system-externality labels and J2/F2 fallback.** Do not spend another round merely increasing merge ownership. Before reopening 4x, add low-overhead progress/event-loop/queue profiling and a resumable bounded worker so the shared capacity boundary becomes attributable. |

## Performance and safety evidence

### Deterministic JIT mechanism

| Workload | J0 mean TTH | J1 mean TTH | J2 mean TTH | J2 delta vs J0 | J2 events/raw bag | J2 multi / mutation | Safety |
|---|---:|---:|---:|---:|---:|---:|---|
| Formal 1x | 217.467307 | 214.905057 | 214.944726 | -2.522581 | 171.645408 | 4,722 / 3,465 | PASS |
| Formal 2x | 1,394.708896 | 959.393343 | 851.864109 | -542.844788 | 223.906932 | 40,226 / 31,257 | PASS |

The J1/J2 fault matrix also passed both distinct temporal gates. The 35% window
preserved pending competition and drained every outstanding request. The
evidence-directed edge-(6,12) window produced exactly one in-flight lease
recovery for each of J0/J1/J2, completed all three affected bags, delivered
fault and repair notifications, and ended with zero outstanding requests.

### Learned merge closed loop

| Scope | Eligible | Applied/owned | Distinct mutation | J2 fallback | Mean TTH delta | P95/P99 delta | Event delta | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 8,192 evidence trace | 935 | 919 | 44 | 16 starvation | 0.000000 | 0 / 0 | -6 | mechanism positive, utility neutral |
| 43,603 capacity | 3,526 | 3,500 | 154 | 26 starvation | -0.004653 | 0 / 0 | +228 | research only |

At 8,192 the paired bag counts were 35 improved, 85 harmed, and 4,778
unchanged; the improvement and harm sums exactly cancel. At 43,603 they were
207, 286, and 28,013. Production authorization remains false independently in
the artifact, runtime grant, and offline promotion gate.

## Evidence boundaries

- The protected 43,603 ladder uses original-entry TTH and reports about 2,490 s;
  the formal scale campaign uses the G10 distribution-preserving release-time
  denominator and reports about 215 s at 1x. These rows test different contracts
  and must not be compared numerically across tables.
- `events/raw bag` uses 28,506 bags at 1x and 57,012 at 2x, not the requested
  segment counts of 43,603 and 87,206.
- Capacity mode preserves authoritative counters but stores no candidate rows.
  Evidence-trace mode is retained only through 8,192 and in narrow fault tests.
- The 4x rows contain external wall-time and resource observations only; missing
  native metrics are unknown, never zero, passed, or failed.

## Recorded next ideas

The evidence suggests four concrete follow-ups, in order:

1. Instrument BOLT-P before adding threads. Merge M0 is a complete but static
   trace proxy: all 935 multi-candidate 8,192-trace opportunities have
   exact-bit local-scoring pack width one after destination/upstream roles are
   unified into the live junction namespace. The trace lacks microphase, event
   sequence, frontier epoch, parent causality and complete dynamic footprints,
   so this is not runtime concurrency proof. Given the single trace and light
   affine scorer, a merge-only `P=4/8` pool is a low-priority engineering
   candidate, not a performance theorem. Measure Source/Route live width,
   event-category CPU, hot-owner skew and proposal/commit cost at 1x/2x; also
   benchmark process-isolated data generation over non-overlapping workloads.
   Implement immutable parallel proposals only where both executable width and
   material compute share are observed, with one deterministic commit lane.
2. Target route/admission at the 2x source-wait knee with local candidate sets,
   bounded counterfactual horizons, and a small set of full-system externality
   pairs. Expose bounded read/write resource keys from the start so this new
   action seam is both causally useful and BOLT-P-ready.
3. Allocate merge research coverage using a shadow
   `will_change_J2_action` gate. Uniform coverage produced only 154 distinct
   changes from 3,500 ownership decisions; causal-action density is the useful
   budget, not nominal ownership.
4. Add sampled event-loop/queue profiling, periodic progress snapshots, and a
   resumable worker before rerunning 4x. This should identify observer cost,
   retry/wakeup amplification, queue-operation complexity, or true capacity
   saturation without raising the event cap or retaining full traces.

The complete method, resource-conflict contract and staged `P=1/2/4/8`
validation path are recorded in
`outputs/reports/g4irsf18_bolt_mapf_parallel_method.md`. It distinguishes
deployment-side concurrent local owners from simulator-side parallel discrete
event execution; neither is used to rewrite the current G18 production or
learning decision.

Two small regression additions are useful but non-blocking: a real pending-cap
overflow/retry/drain fixture, and a direct native test for missing research grant
or non-fixed workload. They should not displace the route/admission or 4x work.
