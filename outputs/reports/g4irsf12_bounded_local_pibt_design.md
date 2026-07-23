# G4IRSF12 Bounded Local PIBT Design

Status: `STANDALONE_PROTOCOL_IMPLEMENTED_AND_TESTED_RUNTIME_INTEGRATION_NOT_CLAIMED`.

## Scope and identity

The implementation is the header-only
`cpp/ics_core/runtime/bounded_local_pibt.hpp`, exercised by
`cpp/tests/test_bounded_local_pibt_real_map.cpp`.

It is intentionally independent of `Graph`, A*/CIE, the global
`ReservationTable`, future routes, and global blocker searches. The caller
must construct one finite arbitration slice from bags that are simultaneously
ready, their one-directed-edge candidates, and the owners of only the local
resources touched by those candidates. The resolver is not wired into
`EventDrivenJunctionRuntime` in this change.

## Protocol

### Deterministic local priority

Every ready bag receives one unique rank using:

1. physical-fault emergency first;
2. minimum deadline slack;
3. maximum accumulated wait;
4. maximum retry age;
5. maximum source-release age;
6. stable bag ID.

All fields are provided in the local slice. Stable bag ID removes the final
tie, so input iteration order cannot change the result.

### Local ownership and inheritance

Candidate claims are opaque local resource keys for such objects as the exact
directed edge, destination/merge slot, entry credit, or queue position. Each
resource has at most one owner. The explicit owner table is authoritative;
optional bag-held resources are checked against it. Moving a ready owner
releases all of that bag's resources present in the bounded owner table for
the current atomic proposal.

Only a lower-priority owner that is present and movable in the same ready
slice can inherit priority. An owner outside that slice, an owner marked
immovable, and every in-transit owner are hard blockers. The resolver never
searches the graph for a missing owner.

P0 through P4 set recursion limits of zero through four. Each recursive branch
has a visiting guard and a full local search-state checkpoint. A failed
candidate, depth limit, cycle, stale fault, or immovable owner restores the
checkpoint before the next deterministic alternative is tried.

### Validate and atomic commit

The result contains at most one one-edge action per bag. Before any callback
can publish an action, the resolver:

- validates that every action is one of that ready bag's exact directed-edge
  candidates;
- validates unique bags and pairwise-disjoint local claims;
- re-reads physical fault state and generation for every selected edge;
- calls `prepare` once with the complete batch;
- re-reads fault state and generation after prepare;
- calls `commit` once with the same complete batch.

Any prepare rejection, commit rejection, callback exception, or fault
generation change after prepare invokes one whole-batch rollback. A fault
failure before prepare needs no rollback because nothing has been staged.

Atomic publication is a callback contract: `prepare` may stage but must not
publish a partial batch, `commit` must publish all or return false, and
`rollback` must undo staging. The resolver records callback counts and whether
rollback itself threw; it cannot make a non-transactional external system
atomic by itself. Slot/credit expiry and resource-version checks other than
the directed-edge fault generation belong in the caller's local prepare
validation and must fail the entire batch.

### Hard local bounds and observability

The default slice limits are 32 ready bags, 16 candidates per bag, 128 total
resources touched across candidates, held sets, and owners, and inheritance
depth four. Exceeding a limit throws before proposal work. Future-release and
in-transit bags also fail closed.

The result exposes candidate attempts, blocker moves, inheritance messages,
owner reads, fault reads/revalidations, cycle guards, backtracks, immovable
blockers, stale candidates, inheritance depth, and prepare/commit/rollback
counts. These are protocol counters, not runtime throughput measurements.

## Test evidence

The CMake/CTest target is `bounded_local_pibt_real_map`. It covers:

- the P0--P4 depth boundary with a four-blocker chain;
- one deterministic priority order independent of input order;
- emergency/deadline/aging priority components;
- priority inheritance and movable blockers;
- a local ownership cycle, visiting guard, and candidate backtracking;
- continuation backtracking across two sibling blockers whose first escape
  choices conflict;
- prepare rejection, commit rejection, rollback, and a fault-generation
  change between prepare and commit;
- in-transit owner immovability and safe hold when no action is feasible;
- exact directed-edge, simultaneous-readiness, and total-resource slice
  validation.

All graph-dependent checks load only
`data/processed/maps/map2.json`. The test discovers, rather than hard-codes, a
real directed merge, a real split with an adjacent movable blocker, and a real
weak-projection bridge. Pure protocol chain/cycle/transaction tests use no
graph fixture.

At the time of this standalone test, the protected map audit reports 54 nodes,
69 directed edges, 23 topological merges, 20 topological splits, 31 directed
SCCs, and 11 weak-projection bridges. These bridge/SCC facts are why the
implementation explicitly sets
`classical_pibt_completeness_claimed = false`.

## Claim boundary

This is accurately described as **PIBT-inspired bounded local coordination**.
It implements multi-bag priority inheritance, blocker movement, backtracking,
a cycle guard, and an atomic one-step action set. It does not establish the
classic PIBT finite-arrival theorem on this directed airport graph, does not
prove deadlock freedom or throughput optimality, and does not provide a
multi-step route.

No runtime completion rate, starvation rate, latency distribution, depth
ablation, or throughput improvement is claimed here. The planned
`g4irsf12_pibt_depth_ablation.csv`,
`g4irsf12_wait_for_cycle_motifs.csv`, and
`g4irsf12_atomic_commit_rollback.csv` must come from a separately reviewed
runtime integration/evaluation; they are not fabricated from unit-test
outcomes.
