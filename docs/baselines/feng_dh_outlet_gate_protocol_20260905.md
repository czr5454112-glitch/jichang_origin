# Outlet-gating diagnostic, preregistered before its run

The full retained-boundary probe completed all bags but produced mean THT
1065.73 s and maximum 9180.2 s. It reveals that combining the inferred 2 s
delay with stationary upstream residence creates a 3.4 s incoming-port
headway. This combination fails the historical numerical gate. It must not
be adopted as a weak baseline merely because it would favor G31.

This next probe separates two unresolved questions: whether a fixed transfer
is allowed to overlap, and whether a bag may leave upstream when its chosen
outlet is already stopped. The second question has a direct motivation in
Feng's revised manuscript p26, step 2(c): stop before the switch when the
first position on the chosen outgoing link has a stopped bag. See the primary
source identities in `feng_dh_primary_semantics_reaudit_20260905.md`.

`FENG_DH_OUTLET_GATE_V3` preserves the repaired control's overlapping 2 s
transit, all existing service durations, coefficients, FIFO and updates. Before
a positive through service releases upstream, re-evaluate the same DH scorer
and keep the upstream footprint and node server if the chosen outlet's first
footprint position contains a stopped bag. Retry this check each tick. A
zero-through service makes the same check before approval. No timer restarts
and no added fixed delay or numerical capacity limit are introduced.

This probes the location of the switch-in HOLD check. It does not establish
the space/capacity of the remaining transit stage. Routing is still re-evaluated
after transit, as in the control; therefore this is not a claim of exact
original switch-out latching. Report the extra decision checks and all results.

Require fixtures showing blocked-positive/zero exits retain upstream,
an open exit still releases after 1 s into overlapping transit, and finite
timer waits do not become deadlock. Then run the full original map2 shared-D
population. The first protocol's input controls and 5% min/mean, 10% tail/max
tolerances apply unchanged. This is a separate diagnostic hypothesis, not a
numerically chosen replacement. No new Nanning or extended runs are authorized.
