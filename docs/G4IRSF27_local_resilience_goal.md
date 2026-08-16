# G4IRSF27 — simple local resilience goal

## Objective

Improve the active S4/J2/E2 decentralized-by-decision framework on the
remaining thesis experiments without turning it back into a centralized path
planner.

The implementation boundary is fixed:

- one next-hop decision at the current node;
- no runtime full A* and no per-bag route suffix;
- no HCA-style global reservation table or global queue scan;
- decision work remains `O(outdegree)`;
- one fixed mechanism and one fixed parameter contract across fault cases;
- the scorer, one-hop commit path, J2 and E2 stay unchanged; the only general
  queue change is the runtime's existing per-junction FIFO option.

## Honest success target

“Strictly win every cell” is not mathematically defined for several Table 5.5
cells. A method cannot exceed a success rate of 1, and it cannot exceed the
directed-reachability upper bound after the interrupted edges are removed.

The registered target is therefore:

- strictly beat fresh HCA wherever its result is below the topology upper
  bound;
- tie fresh HCA where it already reaches the topology upper bound;
- never regress any currently won no-fault cell or a hard-safety invariant;
- keep the source-inconsistent `pair_5_7` cell `NOT_MEASURED` unless its
  original protocol is recovered.

For the 15 measurable Table 5.5 scenarios, the topology-limited best possible
fresh-HCA outcome is 6 strict wins, 9 ceiling ties, and 0 losses. This includes
the two S4 wins already present in G26.

## Minimal implementation candidate

Use the existing local `queue_discipline="fifo"` option at every junction.
This is not a new planner: each node still arbitrates only its own queue. The
previous deadline/aging choice caused the worst 2.5 m/s bag to wait 173 seconds
at node 13 before entering node 23. FIFO reduced that maximum local wait to
46.2 seconds without adding any state or scorer feature.

Use a fault-triggered, goal-conditioned local value fixed point:

```text
D(node, goal) = min over active outgoing edges
                [edge travel time + D(neighbour, goal)]
```

Each node owns only a scalar per active goal. The runtime decision reads the
candidate neighbour's scalar and still commits only one legal next edge. An
unreachable scalar at a source rejects that segment locally instead of
creating useless retries. No bag identity or future route is stored in the
value state.

The first implementation reuses the already audited G24 legal-candidate
residual seam. The value fixed point is produced by deterministic neighbour
relaxation, not by adding another scorer, model, or global reservation layer.
This is a paper-protocol prototype because all Table 5.5 faults start before
the first bag and remain active for the experiment window. A later online
version, if needed, must use local invalidate/relax messages rather than a
central per-bag replanner.

## Canary evidence before implementation

An in-memory prototype using the existing residual seam produced:

| Case, first 512 segments | Original S4 | Fault-aware local value | Topology-reachable segments |
|---|---:|---:|---:|
| `single_4` | 355 completed | 512 completed | 512 |
| `pair_2_4` | not rerun in this probe | 452 completed | 452 |
| `triple_4_6_7` | not rerun in this probe | 291 completed | 291 |

For `single_4`, event count fell from 5,174,112 to 48,747. The two combination
canaries also completed every topology-reachable segment. These results are
only an implementation gate, not final full-day evidence.

## Full fault-matrix result

The same fixed fault-local value mechanism was then run on all 15 measurable
Table 5.5 scenarios. It reached the directed-topology raw-bag upper bound in
every scenario:

- versus fresh HCA: 6 strict wins, 9 topology-ceiling ties, 0 losses;
- versus the archived paper rates: 10 wins, 5 ceiling ties, 0 losses;
- `pair_5_7` remains `NOT_MEASURED` because the archived source uses an
  inconsistent scenario-specific edge mapping.

The fault-value extension is exactly off without a fault; FIFO remains the
deliberate local queue policy. The fault values are structural, not learned:
each node reads one scalar per goal and still commits only its current legal
next edge. In this prototype the neighbour rounds are orchestrated in one
Python process, so the evidence supports decision-layer decentralization, not
a claim of a physically distributed deployment.

## Full no-fault FIFO controls

The same FIFO choice was run on the complete 43,603-segment / 28,506-bag input
at all four speeds. All runs completed and passed the registered structural
safety gate. Mean and maximum TTH beat fresh HCA at every speed. At 2.5 m/s,
mean changed from 210.769735 to 210.757078 seconds and maximum fell from
407.404 to 287.804 seconds, below fresh HCA's 357 seconds.

The remaining 2.0/2.5/3.0 minimum differences are only 0.002--0.535 seconds
and lie at the physical shortest-time / clock-resolution boundary. They are
reported as non-wins rather than removed by changing service time or timing
denominators.

## Table 5.4 protocol recovery and speed stop decision

G26's Table 5.4 reconstruction slows every physical edge for the whole day.
The thesis instead says that route planning uses the standard speed and that
the deviated observation updates the bag's real-time position before conflict
prediction or recognition. The retained Java source likewise has one physical
`Edge.v`, while its surviving disturbance fragment is a node-timing
`bias_time`, including `3 * Math.random()`. It is therefore incorrect to use
the G26 sustained derating stress test as the paper Table 5.4 verdict.

The archived raw experiment files reproduce 17 of the 24 dynamic/static cells
in Table 5.4. The 2.5 m/s, 10% static file contains start records rather than
completion records, and all 3.0 m/s raw files are missing. The exact experiment
source version and random seed were not retained, so any executable recovery
must be labelled `LEGACY_VARIANT_RECONSTRUCTION`, not exact reproduction.

The physical lower bound independently confirms the protocol mismatch. Under
whole-day physical derating, the 2.5 m/s, 20% lower bound is 4.3096 minutes
although the archived dynamic result is 4.25 minutes; at 30% the lower bound is
4.9007 minutes while the archived dynamic/static results are 4.49/4.72.
No routing algorithm can beat those archived values under the G26 stress
protocol.

A minimal oracle that scaled the downstream potential by the known speed ratio
was tested on 8,192 segments for the only close feasible stress cell
(`2.0 m/s`, 20%).
It made 196 committed route changes and slightly worsened mean time from
334.009878 s to 334.011027 s. The speed-EWMA idea is therefore stopped; no new
speed module will be added. Before a 12/12 speed claim can be pursued, the
original paper's actual disturbance scope and timing must be recovered. The
minimal recovery candidate keeps nominal travel speed and injects a fixed-seed
node-observation delay `delta ~ U(0, k seconds)`, with `k = 1/2/3` for the
10/20/30% levels, matching the surviving `bias_time` family. A future live
comparator must share the same delay stream; the current archived comparator
cannot. The reconstruction may not add global planning.

This reconstruction was run for all 12 Table 5.4 cells with the single fixed
seed and FIFO local arbitration. All segments and raw bags completed, all
structural safety gates passed, and all 12 S4 means were below both the
archived dynamic and static means. Because the archived comparator cannot
share the missing 2021 random stream, this is explicitly
`LEGACY_VARIANT_RECONSTRUCTION`, not a paired fresh reproduction.

## Staged gates

1. Unit tests: cyclic graph, unreachable branch, deterministic convergence,
   no-fault exact-off behavior, and finite bounded artifact values.
2. 512-segment canaries: `single_4`, `pair_2_4`, `triple_4_6_7` must complete
   every topology-reachable segment with all hard-safety fields clean.
3. Full critical cases: the same three cases must reach their raw-bag topology
   upper bounds. A source-rejected unreachable segment remains a business
   failure and is never counted as completed.
4. Full Table 5.5 matrix: one fixed mechanism, no per-case tuning, all 15
   measurable cells non-inferior to fresh HCA and every headroom cell strictly
   better.
5. Publication: record positive and negative results, keep protocol labels
   separate, and activate the extension only after the complete matrix passes.
