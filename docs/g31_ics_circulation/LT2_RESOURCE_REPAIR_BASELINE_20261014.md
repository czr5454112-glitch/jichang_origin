# Resource-aware repair baseline

`resource_repair_model_001` records 27 new **model-only** strategy runs: three methods, three gates and budgets8/16/35. It makes zero native calls. The selected actions are compared afterward with previously executed native020 actions under the same continuation; this is action-matched validation, not native execution of these strategies. `resource_repair_native_prepare_001` separately preregisters nine actual strategy executions. That prepared campaign has not run.

All methods receive the same immutable owner capture bundle, public physical predictor and35 actions:31 fixed-route departure times plus four initial route2 departure times. Budgets include the incumbent and count unique cached evaluations. Candidate order is lexicographic `(initial_next, departure, later_mode)` before outcomes. The objective minimizes all four predicted job completion times subject to each predicted completion being no later than the incumbent, with zero tolerance. Missing, nonfinite or unfinished predictions cannot pass. Unevaluated actions remain unknown in the full denominator.

`coordinate_strict` requires a strictly improving one-variable move. The stronger `coordinate_plateau` explores a deterministic nonworsening one-variable frontier, including neutral steps. `resource_pair_repair` computes public operation-path overlap, identifies shared nodes1/3/4, destroys both initial route and departure variables, and evaluates the bounded coupled neighborhood. It retains the complete four-job obligation closure. There is no assignment repair, exterior-boundary repair, regret insertion, SIPPS, later-action optimization or general rolling controller.

| Gate, budget35 | Strict coordinate gain | Neutral coordinate gain | Coupled repair gain |
|---|---:|---:|---:|
|0|.009s|.009s|.009s|
|6|.009s|1.410s|1.410s|
|12|2.090s|2.090s|2.090s|

These are model gains. All27 selected actions match already executed, strictly protected native020 outcomes, but the new nine-branch execution is still necessary to establish actual behavior of the strategy wrappers. At gate6 the strict method stops at a local fixed point after32 evaluations, while neutral coordinate and coupled repair both reach the route2/early action with35 evaluations. Thus the initial joint gain is explained by an ordinary stronger coordinate-search baseline; it does **not** establish superiority or novelty of the coupled search. Budgets8/16 retain the gate0/6 incumbent under the declared candidate order. No result-driven order was substituted.

The implementation is a small adaptation of the destroy/repair idea. Parimi and Williams' TAPF-PC method includes successor closure, boundary retiming, task reassignment/regret insertion or fixed-assignment repair, and SIPPS; those are substantial mechanisms absent here. It is not a paper replication. [Primary LNS source, sections4.2–4.5](https://arxiv.org/html/2603.28968v1).

Integrated capacitated pickup/delivery planning and joint MPC provide broader problem formulations involving assignment, routing and scheduling. The present finite two-variable reference does not reproduce those formulations, solve a rolling horizon or establish recursive feasibility. [Chen et al.](https://arxiv.org/html/2110.14891v1#S4), [Zeinaly, De Schutter and Hellendoorn](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/15_019.pdf).

The underlying predictor and its existing guards are unchanged. Its twelve1ms residuals from all117 validation cases remain; the model has no certified error bound. Reported model-compute times exclude capture, transport, native execution and delivered ACKs, so they do not certify the complete-request100ms target. Five pure repair tests cover neutral reachability, budget denominator, strict protection, obligation closure and unsupported continuation; three wrapper tests cover verified-delivery withholding, fresh local revalidation and actual route2 command submission.
