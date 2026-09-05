# Map2 fidelity re-audit protocol — 2026-09-05

The user's latest request reopens the reconstruction assumptions and gates all
new Nanning and expanded numerical experiments on map2 fidelity. Earlier
feedback documents and accepted assumptions are evidence to review, not a
reason to retain an unsupported implementation or to force a G31 win.

## Fixed observations and controls

- Reference: original DH comparison workbook, SHA-256
  `e8ee03fe5c75fff2bec88251566521e3e6283d549f5676be624c55e050f771fb`.
- Original map2 and inputdata, 28,506 raw bags and 43,603 segments; frozen
  shared-D schedule. THT is the per-raw-bag sum of segment completion E minus
  D. Do not substitute first admission or raw input entry time.
- Reference seconds: minimum 213.3, mean 265.592131481, P95 336.9,
  P99 384.595, maximum 517.2. Full-population throughput is 28,506.
- Speed 2.5 m/s, tick 0.2 s, footprint 1 m, map/input/release identity,
  moving/stopped penalties 0.4/0.8 s stay fixed for the first diagnostic.
- Preserve executable source `809d069832da3fec5a2aa6302a99a9ede24fcd5a1fb28c4a53c3cc3c139ff86f`
  and all its old results. Use separate source, build and output paths.

## First hypothesis, recorded before its new full-population result

Feng's revised manuscript p26, step 2(c), and reviewer response P113 say a bag
stops **before the switch** when a stopped bag occupies the outgoing entrance.
The current implementation releases its upstream footprint after the map
through stage, then permits unlimited off-edge residence during and after the
two-second transfer timer. Downstream blockage therefore need not propagate
upstream. The source text does not establish such an unbounded buffer.

Test `FENG_DH_RETAINED_BOUNDARY_V2`: retain the upstream footprint during the
existing two-second transfer and any subsequent entrance HOLD. Release the
one-second node server at its original time. Remove upstream occupancy only
when actual downstream admission succeeds. This retains one waiting head per
incoming link and does not turn the whole three seconds into a node-wide
exclusive server. All routing, timing and demand controls above remain fixed.

Validate one-shot positive/zero services, backpressure at a blocked junction,
two incoming ports, eventual completion, and lattice non-overlap. Then run
the entire original map2 day. A first-1,000-bag subset is not interchangeable
with the whole-day reference and cannot reject the model on numerical grounds.

The fixed two-second duration itself is still an inferred, potentially wrong
assumption. A retained-boundary result alone cannot authenticate that duration.
Any next hypothesis must be tied to primary-source or trajectory evidence and
recorded before its outcome. Record all tested interpretations, including poor
matches; do not choose delays or penalties to obtain the desired ranking.

## Advancement gate

As an engineering definition of 'close', fixed before this new result, require
all 28,506 bags to complete, relative errors no greater than 5% for minimum and
mean, and 10% for maximum, P95 and P99. These tolerances are our audit criteria,
not criteria published by Feng. Also require successful physical checks and
primary-source review of the state machine. Check per-OD and temporal signatures
to avoid mistaking an aggregate fit for semantic fidelity.

Numerical agreement is necessary for advancement under the user's request,
but is not proof that the missing original DH source was recovered. If this
gate fails, keep new Nanning/expanded runs blocked and continue map2 diagnosis.
Do not use G31 performance to choose a reconstruction. G31 comparison follows
only after a defensible baseline passes this gate.
