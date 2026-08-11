# G4IRSF20 final joint decision

Selected research mainline: **Source A0 + Route S4 + Merge J2 + event-hotpath
E2**, under the unchanged E4/R3/P2/Q0/C0 safety/resource boundary. E2 removes
redundant event work while preserving the measured 1x/2x task timings and
bounded action projections. This remains a simple decentralized, MAPF-style,
one-hop controller. It does not add a centralized route planner, a future-route
fallback, or a new wakeup framework.

The Route campaign has a deliberately narrower contract than a deployable
policy: it labels S4 against one primary alternative at 1x. It does not label
every legal next edge or WAIT. Consequently its current promotion gate is a
**primary-pair data-contract no-go**. That is not evidence that learning itself
has failed, and it is not permission to call an offline model active.

## Required direct answers

1. **Are PR #4 and G20 CI green?** The frozen handoff records the G19 GitHub
   gate as Run #63 `success`. G20's local release gate is a clean MSVC build,
   30 G20 focused tests, 10 Route feature/model tests, and 116 G19 compatibility
   tests, all passing. Remote CI remains the authoritative PR check and is not
   pre-declared from local results; its live status is reported with the PR.

2. **Which events did the G20 hotpath remove?** E1 suppresses known redundant
   source-dequeue, service-complete, and successful-dispatch companion beacons.
   E2 retains E1 and also suppresses a hold beacon only when the post-purge
   queue length, scheduled-incoming count, and reservation time are unchanged
   and the existing safety conditions permit it. The existing pending JIT Merge
   opportunity is still scheduled, so this does not remove its liveness effect.
   At 1x E2 cuts beacon events 1,978,963 -> 1,186,398 (-40.05%) and total events
   4,857,316 -> 4,064,751 (-16.32%). At 2x the corresponding changes are
   4,620,693 -> 2,687,019 (-41.85%) and 11,388,415 -> 9,454,789 (-16.98%).

3. **How did 4x events/s, events/completed, and 60-second completion change?**
   In the matched bounded slice, E0 -> E2 is 92,885.12 -> 82,213.57 events/s
   (-11.49%), 206.493 -> 177.061 events/completed (-14.25%), and 26,977 ->
   27,760 completed segments (+783, +2.90%). The lower events/s is diagnostic:
   E2 deliberately removes cheap events, so it is not used alone as a throughput
   claim. Beacon reduction passes the mechanism gate, but the small completion
   gain shows that event overhead was only part of the 4x boundary.

4. **Where are the 90 S4 mutations concentrated?**
   This was **not re-localized**: the frozen G19 artifacts record 90/27,418
   matched mutations but do not persist membership keys for a node-level
   distribution. The closest, non-equivalent G20 observation is that all 102
   beneficial primary alternatives have wait age below 30 seconds; none of the
   3,147 eligible long-wait groups is beneficial.

5. **Do those states have a generalizable local pattern?**
   There is a descriptive sampled pattern, not a validated policy rule. The
   grouped split has zero contamination across 4,630 raw-task groups, and
   tiny-MLP/F2 makes 6/6 beneficial selective proposals on validation and 3/3
   on audit. Audit support is only 3, below the required 5, and the action set
   is incomplete, so generalization beyond the 1x primary-pair population is
   not established.

6. **How many exact-state Route choice groups were generated?**
   **5,022 completed exact-state primary-pair groups**, containing 10,044
   candidate-action records. This value counts completed matched
   counterfactual groups, not census addresses selected for later replay. The
   associated primary-pair, wait-age, and system-horizon support is
   5,022/5,022 complete eligible pairs, including 3,147 wait-age >=30-second
   groups and 520 H_system groups. The campaign screened 7,500 candidates,
   rejected 2,478 as ineligible, and met every registered sampling target.

7. **What is the H_local/H_region versus H_system error rate?**
   **Not evaluated**: no H_local or H_region labels were collected. Within the
   520 H_system rows, segment-cohort and raw-bag diagnostic signs agree in
   520/520 cases. The direct affected-segment label and raw-bag diagnostic are
   opposite-signed in 59/520 cases (11.35%), plus eight cases where only the
   system diagnostic is zero. This is a scope discrepancy, not an
   H_local/H_region error rate. H_system is diagnostic/veto evidence in this
   campaign, not a claim that the 1x primary-pair utility labels a complete
   system-level action set.

8. **Which feature group materially reduces state aliasing?**
   None is proven because the artifacts contain no controlled alias-collision
   experiment. F2 (S4 core plus current-owner state) is the strongest numerical
   hint with tiny MLP: audit regret is 0.196464 versus S4's 0.210257, with 3/3
   beneficial proposals, +0.013793 s mean advantage, and +0.000136 s LCB90.
   Its support is below 5, so this is suggestive, not an aliasing result.

9. **How much do S4 core, trend, ETA, and two-hop features each contribute?**
   F2 is the best numerical ablation but only at 3/3 audit proposals. F1's
   urgency/history additions do not improve tiny MLP over F0; F3 makes no
   selective proposals. Adding two-hop pressure in F4 is worse than F5 without
   it (-0.005611 s versus -0.000041 s selective mean advantage, both with
   negative LCB90). Planned window trends and ETA summaries are absent and
   therefore **not evaluated**. Only features present in the native sidecar may
   be credited; missing planned trends, ETA summaries, grants, or other fields
   are not zero-filled and are not described as tested.

10. **Which of residual, tiny MLP, and set scorer is best?**
    No family wins the grouped-audit gate. The exploratory ordering is tiny MLP,
    set scorer, then linear residual. Tiny-MLP/F2 has 3/3 beneficial audit
    proposals and positive LCB90 but support 3 < 5. Set-scorer/F2 has 2/2
    beneficial proposals but negative LCB90; its support-qualified F0 result is
    only 3/5 beneficial with 40% harmful. Linear residual applies no selective
    changes. The answer uses the grouped audit split and
    risk-adjusted advantage gate, not training accuracy alone.

11. **Can the standalone learner work without the S4 score?**
    **Not evaluated as a separate experiment.** The score-free set scorer was
    evaluated but failed the audit gates; it is not relabeled as the omitted
    standalone MLP. An offline result, if present, remains an
    offline candidate because the complete-action data contract is not met.

12. **How many Route actions did the model change at 1x and 2x?** 0 and 0 in
    native normal flow. No learned policy was authorized for closed-loop use
    after the primary-pair contract check, so no runtime mutation count is
    invented from offline predictions.

13. **What is the beneficial/harmful mutation ratio?** It is undefined for
    native applied mutations because there were none. The completed offline
    primary-pair labels are 102 beneficial (2.03%), 4,892 harmful (97.41%), and
    28 neutral (0.56%), a beneficial:harmful ratio of about 1:47.96. The best
    tiny-MLP/F2 audit result proposes three changes, all beneficial, but remains
    below the support gate;
    those statistics must not be relabeled as an applied-runtime mutation ratio.

14. **What is the S4 fallback ratio and why?** All native Route actions remain
    under S4, which is 100% non-learned handling for this G20 decision. This is
    a data-contract decision—not a measured risk-abstention rate and not proof
    that the model failed. The pair labels omit the full legal action set and
    WAIT, so promotion would overstate what was supervised.

15. **Do 1x mean/p95/p99 avoid regression?** Yes for the promoted E2+S4
    research baseline: E2 has exact per-task TTH parity with E0/S4 at mean
    213.912317 s, p95 252.004 s, and p99 281.004 s. Hard-safety results and the
    measured final/count/last-eight action projection also match. The latter is
    a bounded projection, not a full action-trace equivalence claim.

16. **How much do 2x mean/source/route/network times improve?** E2 alone has
    zero measured business-time improvement: mean remains 337.842709 s and the
    complete per-task TTH plus aggregate Route-wait projections match E0. The
    frozen G19 source-wait reference remains 54.666355 s. No learned 2x
    closed-loop run was authorized, so a fresh Source/Route/network improvement
    decomposition is not fabricated from offline pairs.

17. **How much of the v2-safe gap is closed?** 0.000000 s/bag, or 0%. E2 keeps
    the 2x S4 mean at 337.842709 s versus v2-safe at 247.384666 s, so the gap
    remains 90.458043 s/bag.

18. **Does G20 reach Gap-25, Gap-50, or Strict win?** No, no, and no. No learned
    candidate crossed the data gate into a 2x closed-loop comparison, and the
    semantics-preserving E2 optimization cannot close a TTH gap.

19. **Should Source be reopened?** No. The registered reopen condition requires
    a learned Route policy to improve network time while 2x source wait remains
    the dominant residual gap. G20 did not establish that premise, so A0 stays
    frozen and no new admission learner is added.

20. **Does 4x complete, and what is the physical/software split?** It does not
    complete. E2 reaches 27,760/174,412 segments in the matched 60-second slice,
    below the 50,000-segment full-run unlock gate. The boundary remains mixed:
    E2 proves reducible software event work, but a 14.25% reduction in
    events/completed produces only 2.90% more completions. This leaves a mixed
    boundary: physical queue pressure and residual runtime work remain, and the
    current evidence cannot assign a defensible percentage to either one.

21. **Is BOLT-P P=1 strictly identical to serial?** G20 did not reopen BOLT-P.
    G19's P=1 parity remains inherited background evidence, but E2 plus an active
    learned Route policy did not enter a new G20 P=1 campaign. Therefore no new
    G20 parity claim is made.

22. **Do P2/P4 obtain single-instance wall benefit?** Not evaluated and not
    claimed. The prerequisites were not met: the learned Route policy was not
    promoted, 4x stayed below its unlock gate, and no qualifying live-width plus
    model-cost result justified adding shared-runtime workers. Existing
    process-isolated rollout parallelism remains data-generation infrastructure,
    not single-instance BOLT-P speedup.

23. **Are fault and late/stale-proposal paths safe?** The tested E2 boundary is
    safe for immediate notification in both protected 8,192-segment-prefix
    scenarios. The pending/in-flight repair case completes 10/10 affected bags and the exact
    in-flight lease case completes 3/3; both have zero physical fault-edge
    entries, equal complete per-task TTH, equal bounded action projections, and
    no failed/conflict/unsafe final state. Delayed or dropped notification was
    not evaluated. G20 also did not run BOLT-P proposal/commit injection, so
    stale-policy or late-worker-proposal safety is not claimed.

24. **Is learning now the normal-flow Route main controller?** No. S4 remains
    the normal-flow controller. The formal offline campaign/model result is
    **PRIMARY_PAIR_DATA_CONTRACT_NO_GO**: the campaign is complete,
    leakage-free, and split-contamination-free, but the full legal action set
    and WAIT are not labeled; no feature/model pair passes every gate, no policy
    is exported, and no family is selected. The known primary-pair-only contract
    is insufficient to activate a policy because it does not supervise every
    legal edge or WAIT. This conclusion preserves a useful dataset and model
    comparison without calling learning failed or active.

## Promotion decision

- **Promote for the next research branch:** E2 as the small event-hotpath
  optimization, with A0 + S4 + J2 kept as the decentralized control mainline.
- **Retain as offline research evidence:** the exact-state primary-pair Route
  campaign and grouped model comparison.
- **Do not promote:** a learned normal-flow Route controller, Source reopening,
  full-4x completion, or shared-runtime BOLT-P P2/P4.
- **Production status:** not authorized; fixed-map research evidence only.

Detailed evidence is in `g4irsf20_event_hotpath.md`,
`g4irsf20_fault_regression.md`, `g4irsf20_route_counterfactuals.md`,
`g4irsf20_route_learning.md`, and `g4irsf20_new_ideas_and_evidence.md`.
