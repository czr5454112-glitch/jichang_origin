# Actual later current-state profiling

## Scope and execution

- Input is the new `g31_ics_learning_next_20261017/later_episodes_001/guarded_default/episode/native/raw.json.gz`, not the old initial 96-candidate data.
- A uses the actual 7.339999999999996 first-return evidence; B uses the actual 9.689999999999994 first-reuse evidence, including the delivered E3→4 and P9→3 entries.
- No native session, fork, model source modification, changed protection reference or cross-event cache is used.
- The first 60-second Job exited 1 after 3.328 seconds: only the diagnostic result signature incorrectly rejected tuples in the inherited internal event trace. Its original plan, four stage results and failed report remain intact.
- `repaired_002` changes only the probe's result signature to canonical JSON wire encoding. It exited 0 after 11.328 seconds under the same 60-second hard limit. All 11 paired result signatures match, and all loaded project source pins are unchanged.
- Each stage has one unprofiled invocation and one cProfile invocation. These are narrow diagnostic samples, not a latency distribution, native critical-path measurement or a 100 ms certificate. Per-stage preparation, result signing and file export are outside its timer.

## Measured costs

| Stage | A unprofiled ms | B unprofiled ms | A profiled ms | B profiled ms |
|---|---:|---:|---:|---:|
| `build_seed(evidence)` | 227.461 | 277.459 | 757.830 | 985.170 |
| `revalidate_seed(saved_seed)` | 235.285 | 349.721 | 765.603 | 1035.229 |
| `Projection` initialization only | 1.263 | 0.780 | 4.415 | 4.095 |
| Inherited event loop, including current seeding | 4.081 | 3.624 | 11.277 | 9.037 |
| Two separate `predict(seed, action)` calls | 614.608 | 681.829 | 2003.607 | 2029.583 |

The inherited `physics.check_sources()` took 1.202 ms unprofiled and 1.202 ms profiled, with three file reads. It is called when constructing `current_run()` during module import, **not on every current `predict()`**. This is not the present repeated-candidate bottleneck. Actual native admission/source-archive costs are outside this probe.

## Root cause

`predict()` calls `revalidate_seed()` independently for each action. Each revalidation calls `build_seed()` again. Each seed build invokes `later_context()` twice: the initial guarded construction and the immutable-context revalidation. Those existing guards in turn repeatedly construct the three static public cases.

For **one** seed build, cProfile records:

- `public_live_obligation_projection.inputs()` / `fixed_contracts()`: **31 calls**.
- `identify_public_case()`: **3 calls**, each scanning all three fixed cases.
- `initial_facts()`: **11 calls**, each re-identifying against the complete fixed catalog.
- `service_aware_potential()`: **620 calls**, all under static `native_host.prepare_input()` construction, not current physical rollouts.
- A `fixed_contracts()` cumulative time: 565.353 ms of 757.830 profiled ms. B: 680.216 ms of 985.170 profiled ms.

For **two candidates**, `revalidate_seed()` consumes 1971.52/2005.54 profiled ms (A/B), approximately 98.4%/98.8% of the two-call wall times. There are **1242** potential constructions: 1240 static-catalog reconstructions and only **two** actual Projection initializations. `fixed_contracts()` alone accounts for approximately 72.0%/64.6% of the profiled two-candidate times.

Largest exclusive hotspots for two candidates are `copy.deepcopy` (530.18/547.13 ms), `service_aware_potential` (203.11/189.51 ms), JSON `iterencode` (143.17/146.76 ms), `_deepcopy_dict` (129.70/139.22 ms), and public-payload recursive checking (91.91/128.20 ms). Cumulative values are nested and must not be summed; the `.prof` files retain caller relationships. Python `deepcopy` is largely work performed for repeatedly regenerated static cases, not evidence that the physical state itself is huge.

## Minimum safe optimization candidates

1. **Build the immutable expected static catalog once per request, not 31 times per seed.** Bind its exact bytes and source/version closure; let all unchanged graph/job/semantics comparisons read that catalog. Do not cache actor observations, delivery status, v3 age, pending actions, entry receipts or result values with it. A request-local catalog avoids an unnecessary cross-event invalidation problem. Preserve exact input/type/schema comparisons, defensive ownership and unchanged accepted native semantics.
2. **Provide a request-scoped two-candidate evaluation entry.** Revalidate the exact seed once at entry and use fresh independent Projection instances per action, sharing only that immutable validated seed and static catalog. Keep action-local copies, installed-preference semantics and all per-action validity checks. The separate execution layer must still verify the real current NativeCollectionAttempt, physical time, current local view, immutable own outbox, candidate identity and original five-job reference immediately before submitting.
3. **Only after (1) and (2), inspect redundant serialization/copying of the same immutable supplied context.** A genuinely fresh factory result may be retained within that same request, but a saved dictionary or caller flag must never become authority. Keep at least the full supplied-data guard and exact integrity validation; do not simply remove `later_context` checks because they are expensive.

No event-loop optimization is justified by these data: its few milliseconds are not the dominant cost. Do not claim that sharing an expensive guard makes the current-state projection physically certified. B at 10.22 after A's delayed return is a **new** collection and must be seeded/revalidated anew; its old initial04 reference must not be refreshed to the delayed current incumbent.

## Acceptance for a future patch

- Compare every candidate's canonical full prediction and exact five-job completion to this source version, using both A and B saved actual contexts, plus the actual delayed-A/B10.22 context.
- Retain stale generation, moving target, expired/undelivered v3, missing entry, wrong owner, pending request, changed outbox and mutated-static-catalog refusal tests.
- Verify that nondefault candidates are still really evaluated and are rejected for the same strict positive per-job deltas, rather than silently masked or rebaselined.
- Measure full new request boundaries separately after implementation. These samples are diagnostic evidence, not the resulting optimized performance claim.
