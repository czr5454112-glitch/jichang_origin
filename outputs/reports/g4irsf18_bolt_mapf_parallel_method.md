# BOLT-MAPF / BOLT-P parallel local-control method

Status: **`METHOD_RECORDED_M0_TRACE_BUCKET_PROXY_COMPLETE_PARALLEL_EXECUTOR_NOT_YET_IMPLEMENTED`**.

## Direct answer

Yes, as an architecture direction: compared with this repository's old
sequential full-route reservation loop, G18's merge boundary exposes an
owner-local proposal interface that can be evaluated separately when its full
runtime footprint is independent. The important qualification is that
BOLT/G18 proposal ownership has not yet been extended to Source or Route; both
remain under F2, and the native simulator still processes one global event heap
on one thread. The repository does not yet contain an executable independent
frontier or a measured multi-core speedup.

This report records two related method names:

- **BOLT-MAPF**: *Bounded One-Hop Lease-based Temporal Coordination for
  Decentralized Lifelong MAPF*. This is the local coordination method already
  partially realized by G18's destination-owned bounded pending sets, natural
  service opportunities, generation validation and short exact leases.
- **BOLT-P**: the proposed deterministic parallel execution protocol for
  BOLT-MAPF.
  It uses immutable snapshots and parallel proposal computation, followed by a
  single canonical validate-and-commit lane.

The split is deliberate. BOLT-MAPF describes the algorithmic ownership and
coordination boundary; BOLT-P describes the intended invariants for exploiting
that boundary without changing ordering, safety, fairness or fault semantics.

## Why the legacy batch has a longer serial dependency

In the read-only legacy implementation, `ICS_PathFinding.java` removes one
unfinished task, calls `Astar.research`, saves its route and immediately writes
that route into the shared constraint table before processing the next task.
The next route therefore observes the previous route's reservation update.
That is a real priority/reservation dependency chain inside this project's old
batch loop.

For one legacy scheduling pass, its project-specific work is approximately the
sum of each attempted task's path-search cost plus reservation updates; tasks
returned to `unfinishTasks` add later attempts. The critical path contains the
ordered shared-table writes. This is not claimed as a lower bound for every
possible HCA* implementation: speculative, windowed or partitioned HCA*
variants may expose some parallel work. It characterizes only the legacy path
present in this repository.

BOLT-MAPF does not reserve a complete future route. A resource owner observes
at most `K` local pending requests, evaluates fixed-dimensional local features,
and issues one short exact lease at a natural service opportunity. With fixed
`K` and feature dimension `d`, candidate filtering/scoring is `O(Kd)` and the
pending subset is `O(K)`. A complete owner step also pays for local calendar,
queue, active-grant and commit work; those structures are not bounded by `K`
alone. The verified separation currently applies to Merge proposals, not yet to
Source or Route ownership.

## Verified starting point

The following are repository facts, not proposed results:

- The native runtime has one `RuntimeEventQueue`, implemented as a priority
  queue ordered by `(time, microphase_priority, seq)`. `drain()` repeatedly
  calls `process_one_event()`, which pops and fully processes one event.
- There is currently no worker pool or thread-safe single-runtime execution
  path. The Python binding also does not release the GIL around this runtime.
- Destination merge state is already partitioned by destination node. Each
  owner has a bounded pending set (configured cap `64`), local lifecycle state,
  a generation, a coalesced wakeup and short exact capabilities.
- Staged event publication, exact calendar preparation, generation rechecks,
  deterministic event sequence numbers and checkpoint-safe boundaries already
  provide most of the transaction vocabulary needed by BOLT-P.
- Existing G14 same-timestamp instrumentation observed source release batches
  whose maximum size rose from `16` at the 144 tier to `310` at the 8,192
  tier. This proves that coincident trace records exist; it does **not** prove a
  310-wide decision frontier, separable work or speedup.
- G18 J2 produced `4,722 / 40,226` real multi-candidate opportunities and
  `3,465 / 31,257` service-order mutations at 1x/2x. At 2x it completed all
  `87,206` segments and reduced mean TTH by `542.844788` seconds versus eager.
  These results verify the local decision seam and load value, not parallel
  execution.
- All three 4x arms were wall-censored at 1,200 seconds without a native
  return. This motivates attribution and profiling, with parallel execution as
  one candidate; it does not identify event-loop serialization as the sole
  cause and does not prove a physical-capacity limit.

### M0 trace census result

The first zero-thread measurement is now complete on the protected 8,192 J7
merge trace:

| Scope | Opportunities | Exact-bit time buckets | Max bucket | P95 bucket | Max local-scoring pack | P95 pack | Opportunity share in multi-score buckets |
|---|---:|---:|---:|---:|---:|---:|---:|
| All merge opportunities | 27,153 | 25,439 | 2 | 2 | 2 | 1 | 0.022% |
| Multi-candidate/model-eligible | 935 | 920 | 2 | 1 | 1 | 1 | 0.000% |

The input is complete: the companion result reports `28,352` total/stored
candidate rows and zero dropped rows. The screening keys conservatively unify
destination and upstream roles into one junction namespace, then add candidate
request and directed-edge keys. Under that local-scoring abstraction, none of
the 935 action-relevant multi-candidate opportunities belongs to a pack wider
than one. Together with the current small 18D affine scorer, this makes a
merge-only `P=4/8` worker pool a low-priority engineering candidate until CPU
share is measured; it is not a theorem that merge parallelism can never help.

The executable census is in
`scripts/eval/analyze_g4irsf18_parallelism_census.py`; compact results are in
`outputs/tables/g4irsf18_parallelism_census.json` and
`outputs/reports/g4irsf18_parallelism_census.md`. Exact-bit time buckets can
contain causally ordered events and can split runtime-epsilon-equivalent times.
The trace also lacks microphase/frontier epoch, event sequence, parent causality
and dynamic PIBT footprints. M0 is therefore a partial-key local-scoring proxy,
not an executable frontier, commit width or maximum-independent-set result.

## Two different forms of scalability

### Target deployment-side concurrency

The target physical deployment lets source, junction and destination resource
owners operate asynchronously. Two owners with proven-disjoint local resources
could score and prepare their next actions at the same wall-clock time. New
orders could enter continuously without a global full-path batch barrier.

This is an architectural objective, not a completed distributed-system result.
Communication delay, asynchronous fault visibility, controller failover and
distributed backpressure cost have not been measured.

### Simulator-side parallel execution

The offline simulator does not become faster merely because the controller is
decentralized. It needs a parallel discrete-event execution path that preserves
causal time and deterministic commit order. BOLT-P is the proposed path. The
first implementation should parallelize pure computation and retain a single
commit coordinator; it should not make the existing mutable maps and event heap
concurrently writable.

## BOLT-P protocol

For each minimum logical `(event_time, microphase)` frontier:

1. **Freeze.** The coordinator drains the frontier into canonical event order
   and creates immutable, versioned local snapshots. Fault/repair visibility
   for that microphase is fixed before normal decisions are evaluated.
2. **Declare footprints.** Each opportunity declares bounded resource keys it
   may read or write: bag, owner node, corridor, destination calendar/controller
   and fault generation. The declaration contains IDs and generations, never
   pointers into mutable containers.
3. **Partition.** Build a resource-interference graph. Two opportunities are
   adjacent when they may write the same resource, one writes a resource the
   other reads, or one causally creates the other. Stable resource IDs and the
   original event sequence determine partitions and tie breaks.
4. **Compute in parallel.** Workers run only pure candidate construction,
   local feature extraction, J1/J2/J7 scoring, ready-slot calculation and
   proposal assembly. They cannot mutate bags, calendars, controllers, global
   policy counters, traces or the event heap.
5. **Validate and commit.** The coordinator visits proposals in original
   `(time, microphase, seq)` order. It rechecks bag state, queue/controller and
   calendar generations, exact-slot availability, corridor/fault generations
   and the learned-policy epoch. A valid proposal commits atomically.
6. **Recompute conflicts.** A later proposal invalidated by an earlier commit
   is recomputed from the new local state or follows the existing hold/retry or
   fail-closed fault-revoke path. Thread completion order never chooses a
   winner.
7. **Publish.** Child events receive deterministic sequence ranges derived from
   parent order and local ordinal, then are merged into the global heap only
   after the phase commit barrier.

Conceptually:

```text
minimum time/microphase frontier
        -> immutable local snapshots
        -> conflict graph / stable partitions
        -> parallel pure proposals
        -> canonical generation validation
        -> single atomic commit lane
        -> deterministic staged-event publication
```

This is resource-local optimistic execution with deterministic serialization,
not a lock added around the entire existing runtime.

## Conflict contract

| Boundary | Parallel compute is safe when | Must remain ordered at commit |
|---|---|---|
| Source | different owner snapshots and no shared outgoing capacity | source queue, selected bag, outgoing corridor/calendar |
| Route | bounded candidate scoring reads disjoint snapshots | selected bag, chosen edge, downstream capacity; PIBT expands the whole footprint |
| Merge | different destination owners and disjoint corridors/calendars | same destination pending set, grant generation and exact lease |
| Fault/repair | unrelated edge summaries may be prepared separately | affected edge generation is a barrier before dependent actions |
| Learned J7 | feature/scoring calls are read-only and model weights are frozen | coverage/applied counters, kill switch and fallback policy epoch |
| Event publication | workers return staged child-event descriptions | global heap and global event sequence allocation |

The first implementation must avoid retaining `PendingRecord*` across a worker
boundary. Pending-vector mutation can invalidate those pointers. It must also
preserve the current prepare/commit/rollback generation assumptions of local
calendars; concurrent mutation between prepare and commit would otherwise make
an apparently valid lease unsafe.

## Work, span and expected benefit

Let `C` denote the local calendar interval count inspected per candidate and
`C_commit` the remaining local queue/calendar/grant commit cost. A more honest
high-level work model for the current serial simulator is

```text
W_serial = O(T * (K(d + C) + C_commit + log Q))
```

where `T` is the number of processed events and `Q` is the global event-heap
size. This is an upper-level decomposition, not a tight bound for every event
type. Aggregate runtime state includes per-owner pending sets plus calendars,
active queues and grants. BOLT-P does not remove total event work or physical
congestion. It can reduce only the compute part of the critical path when an
instrumented live frontier contains several non-conflicting owners. If `W` is
total work, `S` is the longest causal span including canonical commit, and `P`
is worker count, speedup is bounded by `min(P, W/S)` and the serial fraction.

Consequently, larger order volume helps parallel utilization only while it
creates independent local opportunities. If most work concentrates on one
merge, one corridor, the global heap, or repeated retries, the conflict graph
narrows and speedup saturates. Parallel computation also cannot increase the
physical throughput of belts, service stations or merges.

## Learning and data parallelism

BOLT-P opens three useful learning paths without changing the decentralized
runtime feature contract:

1. **Vectorized local inference.** Feature rows from a proven live compute pack
   can be evaluated as a micro-batch, then returned to their original owners for
   canonical validation and commit. Candidate rows must retain per-opportunity
   offsets/masks so group means, OOD checks, ties and argmax never cross owners.
2. **Process-isolated rollout generation.** Independent runtime replicas can
   use non-overlapping preregistered workload slices, load tiers, fault cases
   and counterfactual pairs. This is feasible now but its throughput has not
   been benchmarked; the current deterministic runtime has no validated rollout
   seed diversity.
3. **Centralized training, decentralized execution.** Offline training may
   aggregate local traces globally, while the exported policy remains limited
   to the fixed local observation contract. Online per-event weight updates
   are excluded from the first BOLT-P version because they would introduce a
   new global ordering dependency.
4. **Keep execution packing out of sampling semantics.** All opportunities,
   including conflicting/hot owners, remain in the dataset. Split future data
   by replica, workload, time block and resource episode; keep matched
   baseline/treatment pairs together and restore original weights after rare
   mutation oversampling.

The current J7 result remains research-only. Parallel inference can lower its
compute cost, but it cannot turn low causal-action density or negligible
business utility into a policy promotion.

## Minimal validation campaign

Implementation should proceed in four small, evidence-producing steps:

1. **Instrument before adding threads.** Merge M0 is only an exact-bit
   partial-key scoring proxy and is narrow for the current action-relevant
   trace. Add microphase, event sequence, frontier epoch, parent causality,
   complete dynamic read/write keys and sampled event-category CPU cost. Then
   measure Source/Route and 1x/2x before selecting a worker boundary. Separately
   benchmark process-isolated data generation.
2. **Pure proposal executor only where width and cost are material.** Add `P=1`
   through the new snapshot/proposal path for a boundary with both executable
   compute width and meaningful CPU share.
   It must reproduce the serial completion, safety, chosen actions and terminal
   state before enabling multiple workers.
3. **Workers `P=2/4/8`.** Measure proposal time, commit time, validation aborts,
   serial recomputes, worker utilization, batch occupancy, events per bag, RSS,
   wall time and CPU time. Compare J0/J1/J2 on matched 1x and 2x inputs.
4. **Reopen 4x only after attribution.** Use capacity telemetry and periodic
   progress snapshots. Separate event storm, heap/commit serialization,
   resource conflicts and physical backlog before considering 8x/16x/32x.

A useful result is not required to be linear speedup. A positive BOLT-P result
requires deterministic serial equivalence, unchanged hard safety, measured live
compute width, and a repeatable wall-time reduction large enough to exceed
worker/commit overhead. If instrumentation shows narrow width or negligible
compute share, the correct result is to optimize event scheduling, use isolated
replicas, or investigate proven spatial lookahead rather than adding threads.

## New ideas recorded with this method

- **Hot-owner affinity.** Keep one owner's proposal work on the same worker to
  reuse feature buffers and reduce cache movement, while the coordinator keeps
  ownership and commit semantics unchanged.
- **Action-first batching.** Batch expensive feature/model scoring, not every
  lightweight event. This targets useful compute and avoids turning event
  dispatch itself into a scheduling storm. The completed merge M0 proxy moves a
  merge-only pool down the priority list for the current trace and affine
  scorer; it does not exclude later benefit under other loads or heavier models.
- **Conflict-width-aware backpressure.** When one resource dominates the
  interference graph, limit speculative work for that owner and spend workers
  on independent components instead of generating proposals that will abort.
- **Source/route co-design.** The verified 2x delay is dominated by source wait.
  A future local route/admission head should expose its resource footprint to
  BOLT-P from the start, so the next learned action seam is both causally useful
  and parallel-ready.
- **Later spatial lookahead.** If instrumented live frontiers are too narrow, a later
  conservative PDES version may partition the map using a proven minimum travel
  time as lookahead. This remains a hypothesis until live-frontier instrumentation
  and a deterministic compute/commit executor are measured.

## Claim boundary

- BOLT-MAPF is MAPF-inspired lifelong local coordination. Completeness,
  optimality and bounded suboptimality are not proved.
- The legacy HCA comparison is an architectural/source audit plus parsed
  historical evidence, not a fresh same-machine HCA benchmark.
- Current G18 is single-threaded. No multi-core, linear-scaling or 4x-capacity
  success is claimed here.
- The proposed parallel executor changes neither production authorization nor
  J7's research-only status. Source and route learned ownership remain zero.
- Fixed `K`, observation radius and feature dimension are part of the bounded
  candidate-scoring contract, not a bound on calendar, queue or active-grant
  state. If any of them grow with global order count, the analysis must be
  repeated.
