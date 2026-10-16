# Delivered-message initial joint prototype

Native020 executed twelve preregistered branches in `native_public_joint_001`: nine normal comparisons and three first-action readiness diagnostics. All nine normal branches completed the four offered jobs, retained both trays, executed both reuse returns, and passed the existing native physical audit. Source hashes were unchanged. This is a synthetic initial joint proposal followed by the existing v2.1 feedback rule, not a complete rolling MPC or a new solver.

Each owner independently reads its own current native observation, its own delivered planning-command ACK/self-copy and the peer snapshot delivered to it. `native_planning_adapter.py` accepts no caller snapshot in its native collection entry point; the loaded extension identity, typed digest, source/target, capture/delivery/ACK times, expiry, coverage and local state are checked. Pure dictionary validation never certifies delivery. The model remains conditional and cannot certify physical protection.

Planning commands are submitted at .05, natively captured at .060000000000000005, delivered at .07 and self-ACKed at .09000000000000001. Decisions occur at .11. L is loading when captured and becomes loaded at the native-captured committed load-completion epoch .1. The adapter explicitly projects this transition and checks this owner's current state; it does not claim a fresh remote observation at .11. In the legacy model's compatibility structure, `captured_at=.11` denotes the projected state epoch; `source_captured_at`, `source_delivered_at`, `projected_at`, the immutable original envelope and the projection assumptions are all retained. Only the native envelope timestamp represents the actual capture.

The fixed-route model evaluates the same 31 public-duration departure candidates as the stronger finite reference. The joint model adds four initial route2 candidates. Neither consumes native forks, outcome tables or gate labels. The first action is followed by the same actual transfer-rejection recovery and later route rule in every normal arm.

| Gate | Fixed-route gain vs incumbent | Joint gain vs incumbent | Joint gain vs fixed-route model | All four strict zero-regression checks |
|---:|---:|---:|---:|---|
|0|.009s|.009s|0|pass|
|6|.009s|1.410s|1.401s|pass|
|12|2.090s|2.090s|0|pass|

At gate6 the receiver physically completes at6.6 instead of8.001 under the fixed-route model, while loaded/reuse1/reuse2 completions are exactly equal. These checks use native business completions after the experiment, not model estimates or a tolerance. The finite candidate domain is not a continuous optimum. The model's earlier all117 validation still contains twelve 1ms completion residuals; its error bound is not certified.

`independent_reassessment_002.json` rechecks all twelve saved rows, original inputs, archived sources, native self-copies and peer capture equality, owner-specific deterministic proposals, ACK/actual-edge execution, all four completions and reuse audit. The first reassessment is retained: it reported mismatches because JSON turns integer resource-map keys into strings; the second normalizes that representation only. The actual native results did not change.

The original readiness row named `lost_A_self_ack` had an incorrect preregistered interpretation of `drop_ack_packets=3`. Native initializes the drop counter independently for every immutable request; both owners lacked self-ACKs and withheld. Delayed publication and expired snapshots also caused both owners to withhold. These three rows are readiness probes only; no business/protection comparison is asserted.

`native_planning_asymmetry_001` separately preregistered one dropped ACK per request and an exact B-only planning retry at .075. B's retry ACK arrived at .105; A still lacked its self-copy at .11. A withheld its route action while B selected route2/early supply and physically entered E's5→1 edge at .22. Thus two snapshot messages do not establish atomic joint agreement. This diagnostic ends at .5 and reports null business metrics and protection `not_assessed`; no hidden shared fallback repairs the split action.

The first adapter/driver test set has27 pure passes and one separately executed native conformance pass. Complete-request100ms, fault-tolerant atomic agreement, generalized aged-state projection, later-checkpoint joint optimization and original-map business benefit remain unproved. The original-map intervention's separate native019 feasibility gate rejected its first route at node112 because the unchanged two-second command arrived after the prefix committed.

## Why normal protected cases do not establish late-feedback efficacy

The protected early joint gate6 case clears E's3→4 traversal by6.4. L only enters7→3 for reuse1 at9.32 and arrives at3 at10.32, so the relevant later resource overlap is absent. In the delayed old window3 case, E wants1→3 at9.61 while L approaches node3. The adaptive7→8 route improves E from12.72 to11.91 with the other three completions unchanged, but11.91 already violates the original receiver incumbent8.01. This is an informative unprotected mechanism, not protected late-feedback success.

A separate outage domain was then preregistered and executed using unchanged jobs, topology, capacities, FIFO and Storage rules. Every outage arm has B unavailable from `.11 + .01/2 = .115` to `2*3 + .1 = 6.1`, derived from public decision/message/receiver-load/node-service durations before outcomes. Initial decisions occur before this exogenous outage and do not read its future schedule.

## Fixed-outage campaign and strong reference

`native_feedback_outage_001` contains117 assessed rows:108 new native020 branches and nine immutable healthy rows reused with exact file hashes and source/binary checks. The new branches include all31 fixed-route timing candidates at each gate; no proposed equivalence collapse was used to omit executions. Native execution took34.823seconds with no source changes. `independent_reassessment_002.json` verifies all117 full-population results, all93 offline reference actions, reused healthy source archives, and identical source-captured inputs/initial decisions before the healthy/outage schedules diverge.

| Regime | Gate | Adaptive feedback gain vs same initial action with native route kept | Joint gain vs fixed-route model | Joint gain vs best protected full31 offline fixed-route reference |
|---|---:|---:|---:|---:|
|Healthy|0|0|0|not part of this outage reference|
|Healthy|6|0|1.401s|not part of this outage reference|
|Healthy|12|0|0|not part of this outage reference|
|Outage|0|0|0|0|
|Outage|6|.820s|0|0|
|Outage|12|0|0|0|

At outage gate6, adaptive feedback completes the receiver at11.9 versus12.72 with the same initial action and later native route kept. Loaded/reuse1/reuse2 completions are exactly unchanged; both real L returns/reloads execute. At9.26 B has the native A→B service forecast captured6.52/delivered6.53, giving E's next-node interval[9.6,10.7], while B's local node3 is currently empty. B issues actual7→8, executes at9.27, receives the updated ACK9.29, and L enters7→8 at9.32; the paired native-keep branch enters7→3 at that same time. This establishes a causal, strictly protected late-feedback benefit relative to the paired no-feedback controller in this declared outage domain.

The fixed-route control has the same feedback capability and obtains exactly the same11.9 receiver completion. Consequently the outage result is generic feedback efficacy, **not additional joint superiority** over that strong control. The healthy gate6 initial joint gain remains a separate result. Comparing outage performance against healthy performance would measure stress cost: at gate6 the receiver is5.3seconds later, not protected relative to the healthy case.

The full31 offline reference explains the strong control. At each gate, all30 departure candidates at or below5.735 are held by the same source-owner outage until6.1 and have identical completion vectors. The6.11 candidate completes the receiver .01seconds later and is not protected against the outage incumbent. Thus the winner is a30-way tie, not a specially tuned departure. At gate6 its ordinary delivered-forecast feedback selects7→8 for reuse1 and7→3 for reuse2. `fixed_reference_diagnosis.json` retains every candidate, received ACK and physical E timing; these post-execution facts are never proposal inputs.

The later resource interaction is now real, but the current implementation still uses an initial finite joint model plus a hand-written later forecast rule. It does not jointly optimize later route and return timing, generalize to arbitrary checkpoints, provide atomic agreement under ACK asymmetry, or establish an advantage on the original workload. Those are separate remaining design problems; repeating the saturated three-gate timing domain or training labels from it would not resolve them.
