# G4IRSF17 I1 causal support

## Decision

**`PIVOT_TO_G2_I1_FRAME_COVERAGE_NO_GO`** — The current real I1 frame cannot satisfy the source/leg coverage gate; move the primary causal budget to bounded destination merge/service-token G2.

The pilot attempted **512** real-address H_bag opportunities; **248** changed the native winner and **248** passed the same-state and hard-safety gates.  Eligible effects were 18 beneficial, 16 harmful, and 214 neutral.

## Exact effect convention

Every delta is `I1 second-ready treatment - native F2/Q0 baseline winner`; negative TTH, source-wait, network, drain, makespan, P95, and P99 deltas are improvements.  H_bag utility is `-(sum direct TTH delta + deadline penalty)` and is explicitly direct-only.  H_system utility additionally includes realized other-bag sum and CVaR95 tail harm.  Each new deadline miss adds a 3600-second risk penalty.

Other-bag externality excludes both reordered runtime bags.  `CVaR95 harm` is the mean of the worst `max(1, ceil(0.05*n))` values after replacing improvements by zero; it is unavailable, not zero, at H_bag.

## Support gate

Beneficial diagnostic split counts are train/calibration/validation = **10/4/4**, against 32/8/8.  Beneficial coverage spans **1** sources, **9** time buckets, and **1** leg types, against 3/3/2.  Support ready: **False**.

## Pivot gates

* sufficient 32/8/8 beneficial support plus 3 sources, 3 time buckets, and 2 leg types -> state/model audit;
* incomplete support after 128 attempted real addresses -> target 512 addresses;
* a structurally under-covered frame at 512 addresses -> frame-scoped I1 no-go and G2 pivot;
* adequate strata but fewer than 512 live changes at 512 addresses -> optional 1,024-address cap;
* incomplete support after 512 live changed pairs -> I1 support no-go and G2 pivot;
* 128 addresses with zero live action changes -> refresh competitive target telemetry, not a scientific no-go.

H_system was deliberately bounded to **8** sampled opportunities (hard maximum 32); 1 were harmful and the maximum observed other-bag CVaR95 harm was **0.0** seconds.
