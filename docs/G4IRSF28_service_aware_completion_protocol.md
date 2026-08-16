# G4IRSF28 Service-Aware Completion Protocol

## Purpose

G28 closes the remaining measurable thesis-table gap without adding another
planner, learner, supervisor, or reservation layer.  The active runtime remains
S4/J2/E2 with local FIFO arbitration.  The only normal-operation change is a
more faithful static cost-to-go scalar that includes the service time already
present in the airport map.

The registered workload remains the protected 54-node, 69-directed-edge map,
43,603 expanded segments, 28,506 original bags, and the speed-specific fresh
HCA release traces used by G26/G27.

## Single mechanism

For each goal, G28 precomputes one static scalar per node:

```text
H(g,g) = 0
H(u,g) = service_duration(u) + min_(u,v) [ travel(u,v) + H(v,g) ]
```

The existing S4 candidate score continues to read:

```text
travel(current,candidate) + H(candidate,goal) + existing local S4 terms
```

The matrix is built once from the static map.  During a decision, a junction
still evaluates only its direct outgoing neighbours and reads one scalar per
candidate.  Runtime decision cost remains `O(outdegree)`.  No full A*, route
suffix, future-route materialisation, HCA-style global reservation table, or
runtime learning is introduced.

Normal operation is therefore:

```text
S4/J2/E2 + local FIFO + service-aware static local potential
```

For a persistent pre-start edge failure, the already validated G27 structural
goal scalar replaces the normal static value.  Its residual must be constructed
against the service-aware matrix, so the fault value is not accidentally based
on the old travel-only baseline.

## Why this change is legitimate

The simulator already charges a service duration at visited nodes.  The former
travel-only potential could prefer a route with shorter belt travel but more
node service, even when its total physical time was longer.  G28 changes only
the static estimate used to rank neighbouring exits; it does not change belt
speed, service duration, release time, task population, or timing statistics.

At 3.0 m/s, the former minimum was 158.335333 seconds.  The service-aware
potential reaches 158.002 seconds on the physical shortest route.  Fresh Java
HCA reports 158.000 seconds because its zero-service source and sink remain
exactly zero, while the native runtime applies its existing 0.001-second
minimum at both nodes.  Removing those two milliseconds would change physical
service semantics and is forbidden.  The registered conclusion is therefore a
physical/resolution tie, not a fabricated strict win; both round to the thesis
value 2.63 minutes.

## Thesis evidence boundaries

### Table 5.2

All four speeds are rerun with their own registered fresh-HCA release trace.
Every case must complete all 43,603 segments and 28,506 raw bags and pass the
existing no-full-A*/no-future-route/no-global-scan safety gates.

### Table 5.3

The dispersed heuristic executable cannot be recovered.  The archive retains
its output distribution and the thesis rule description, but not the moving
and stopped-bag penalties, update ordering, tie-break, occupancy discretisation,
or cache rule.  G28 therefore compares the final 2.5 m/s S4 result directly
with the archived/paper min, mean, and max.  It does not invent a proxy and call
it exact.

The paper-reported improvement percentages use the paper's rounded minute
values.  High-precision derived values are retained as diagnostics.  A result
that agrees only after applying the paper's reported precision is labelled a
resolution tie.

### Table 5.4

The exact 2021 dynamic/static simulator variant cannot be recovered.  Missing
items include the complete dynamic replanning code, random mapping and sampling
scope, seed, static conflict order, all 3.0 m/s raw traces, and one 2.5 m/s raw
cell.  G28 retains the G27 `LEGACY_VARIANT_RECONSTRUCTION` using nominal belt
speed plus deterministic local observation delay.  Comparisons with archived
dynamic/static values are explicitly unpaired and are not presented as an
exact fresh reproduction.

The older G26 whole-day physical derating matrix remains a separate
`SUSTAINED_PHYSICAL_DERATING_STRESS` family and no longer represents the thesis
Table 5.4 protocol.

### Table 5.5

The 15 measurable interruption scenarios must again reach their directed
topology completion ceiling.  A ceiling tie is a successful non-regression,
because neither HCA nor any other routing method can complete more than the
reachable population.  `pair_5_7` remains `NOT_MEASURED`: its archived workbook
edge label conflicts with the global line mapping and the original simulator
configuration is absent.

The S4 and fresh-HCA interruption numerators use the same canonical 28,506-bag
population and fixed denominator, but they are not paired by each segment's
release epoch.  Their 6-win/9-ceiling-tie comparison is therefore a controlled,
descriptive numerator comparison, not a claim of a segment-release-paired
causal speedup.

## Acceptance

- Table 5.2: no loss among the 12 min/mean/max cells; physical or paper-resolution
  boundaries are ties, not wins.
- Table 5.3: all three S4 times below the dispersed heuristic; mean/max improvement
  exceed the paper; minimum improvement may be a paper-resolution tie.
- Table 5.4: all 12 reconstructed cells below both archived dynamic and static
  values, with `exact=false` and unpaired wording preserved.
- Table 5.5: all 15 measurable cells at topology ceiling; no loss versus fresh
  HCA; unresolved `pair_5_7` remains excluded.
- Every native run preserves the existing structural safety gates and reports
  zero runtime full A*, CIE A*, future-route input, and global scan use.
- Decision-layer decentralisation is claimed; physical multi-process deployment
  is not claimed.

If any full run regresses, the service-aware potential is not promoted.  No
second tuning mechanism is added to rescue a failed cell.
