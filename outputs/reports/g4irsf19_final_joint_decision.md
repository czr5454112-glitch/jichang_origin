# G4IRSF19 final joint decision

Selected research mainline: **Source A0 + Route S4 + Merge J2**, under the
unchanged E4/R3/P2/Q0/C0 safety/resource boundary. S4 is the existing
queue/calendar-aware one-hop rule. This is a simpler decentralized MAPF-style
controller with measured benefit; it is not presented as a learned-controller
or production promotion.

## Required direct answers

1. **Are G18 and G19 CI green?** G18 GitHub Actions Run #61 is green as recorded
   by the execution baseline. G19's fresh local gate is green: 123 focused
   Python tests, three native C++ executables, Python compilation, and whitespace
   checks passed. Remote G19 CI can only start after this commit is pushed, so it
   is not pre-declared green.

2. **How many real Source choices exist?** The learned ordering seam had 62,
   238, and 8,335 evaluations at 144/512/8,192, but 0 alternative proposals and
   0 mutations. The deterministic ADMIT/HOLD gate did expose 30 and 137 distinct
   observed treatment HOLD states at 144/512 (A0 had 0 and 2), but these are
   deferred admissions, not cloned counterfactual bag-choice mutations. Distinct
   2x states were deliberately not collected; retry counts are not substituted.

3. **How many real Route multi-action opportunities exist?** The complete
   8,192 trace has 27,775 S1 branch-opportunity rows. S4 has 27,685 rows; 27,418
   are same-state matched and 90 select a different next edge.

4. **How many Source actions did learning change?** 0. No learned Source policy
   is promoted.

5. **How many Route actions did learning change?** S2, the learned no-absolute-ID
   scorer, changed 0 of 27,775 matched branch actions. The selected deterministic
   S4 rule changed 90 of 27,418 matched branch actions (0.3283%).

6. **What are Source/Route/Merge ownership?** Learned Source ownership is 0.
   S2 configured-scorer ownership is 57,539/59,826 observable Route decisions
   (96.18%), but with 0 mutations and 0 benefit; selected S4 owns
   59,772/59,772 observable decisions (100%) as a deterministic rule. G19 uses
   deterministic J2 for Merge, so learned Merge ownership is 0; the prior G18
   J7 experiment owned 3,500/3,526 decisions and changed only 154.

7. **What is overall F2 fallback?** No defensible cross-head scalar exists
   because Source, Route, and Merge have different opportunity denominators and
   no learned Source denominator. Per head: learned Source and selected learned
   Merge are absent (100% non-learned handling); S2 Route risk fallback is
   2,287/59,826 = 3.82%; selected S4 has 0 risk fallback but is not learned.
   Therefore the overall learned-F2-replacement gate is **not met**, and no
   weighted percentage is fabricated.

8. **Which feature group was effective?** Only the small local S4 group:
   candidate queue length, scheduled incoming, corridor next-available, and
   target next-available, combined with travel time and static potential.
   Removing absolute IDs (S2) and shortest potential alone (S3) changed nothing.

9. **Which of residual, standalone, or set scorer is best?** None has earned a
   learned-model claim. They were intentionally not trained after the action-seam
   evidence failed. The best executed controller is the standalone deterministic
   S4 rule; there is no best learned G19 model.

10. **Did 2x source wait decrease further?** Yes through Route S4: 502.462 s to
    54.666 s (-447.795 s, -89.12%). Source pressure A1/A2 then worsened it to
    66.526/58.779 s, so both were rejected.

11. **Did mean/p95/p99 all avoid regression?** Yes. At 1x they change
    214.945/257.804/295.994 -> 213.912/252.004/281.004 s. At 2x they change
    851.864/4,669.424/7,386.187 -> 337.843/960.004/2,242.954 s. All runs
    complete and pass hard safety gates.

12. **What are rollout P=2/4/8 speedups?** Across two clean full repeats:
    P2 1.863x/1.966x, P4 3.289x/3.330x, P8 5.247x/5.325x. All outputs match P1
    semantically; retries and failures are 0.

13. **What is the live executable frontier width?** The independently executable
    process frontier is verified through width 8. The measured same-runtime Merge
    proposal pack width remains 1, so internal parallel commit is not claimed.
    The largest tested load that naturally completes is 2x.

14. **Is BOLT-P P=1 strictly equivalent to serial?** Yes on the real native G15
    checkpoint/clone seam: deterministic replay parity passes, with 13/13
    action-changing targets applied and no failure, stale rejection, or conflict.

15. **Does native BOLT-P P=2/4/8 have repeatable wall benefit?** Not measured.
    The executable path supports those counts, but historical peak worker memory
    is about 5.27 GiB and P8 is unsafe within this machine's 31.4 GiB envelope.
    The repeatable speedups in answer 12 belong to complete process-isolated
    rollout, not shared-runtime BOLT-P commit.

16. **Is the parallel bottleneck compute, commit, conflict, heap, or hot owner?**
    In BOLT-P P1, compute/replay is 274.198 s versus 0.0015 s aggregation, with
    zero conflicts/stale rejections: compute dominates that seam. At 4x the
    single event loop is CPU-saturated and loses event throughput; this evidence
    does not separate heap from beacon/hot-owner cost, so no narrower attribution
    is invented.

17. **Is the 4x boundary physical, software, or mixed?** Mixed. CPU/wall is
    about 0.98, events/s falls from 238k at 1x to 97k at 4x, congestion-beacon
    events are about 39%, and backlog grows. Both software event processing and
    physical queue pressure are present.

18. **Does 4x complete; if not, is it bounded?** It does not complete in the
    60-second slice. It returns natively as `BOUNDED_PROGRESS` with
    27,872/174,412 completed, 42,566 released, 14,694 active backlog, and no
    fabricated finalization. S1 completes only 18,212 at the same boundary.

19. **Are faults, late messages, and worker failover safe under multiple control
    points?** Partially. Both protected 8,192 fault cases complete with zero
    physical fault-edge entry violations; all 10/10 and 3/3 affected bags
    complete and recovery matches S1. The measured cases have no delayed/dropped
    notification and no injected worker crash between proposal and commit.
    Therefore full distributed late-message/failover safety is not claimed.

20. **Is learning the normal-flow main controller?** No. S2's high nominal
    ownership only copies S1, while deterministic S4 produces the useful action
    changes and business gain. Calling this a learned main controller would be
    misleading.

21. **Does the decentralized framework have measurable parallel advantage?**
    Yes for independent complete rollout/data generation through P8, with stable
    semantic output and wall-time gain. No for parallel commit inside one mutable
    simulator; that remains unproven.

22. **What is the narrowest valuable next pivot?** Keep J2+S4 frozen and target
    the 4x event hot path: measure and coalesce congestion-beacon/duplicate wakeup
    work at the existing same-timestamp boundary, then rerun the identical bounded
    4x slice. Do not resume Source training or build a general parallel event heap
    until this small change moves the live frontier.

## Promotion decision

- **Promote for the next research branch:** J2+S4, bounded progress, and the
  process rollout farm.
- **Do not promote:** Source A1/A2, learned S2, J7 as default Merge, new model
  families, or shared-runtime parallel claims.
- **Production status:** not authorized; fixed-map evidence only.

Detailed evidence is in `g4irsf19_route_closed_loop.md`,
`g4irsf19_source_admission.md`, `g4irsf19_rollout_parallelism.md`,
`g4irsf19_scale_capacity.md`, and `g4irsf19_fault_parallel_campaign.md`.
