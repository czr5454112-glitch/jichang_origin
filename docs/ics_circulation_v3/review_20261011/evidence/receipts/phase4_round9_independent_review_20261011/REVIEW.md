# Round9 storage independent review

2026-10-11. No commit/push or C++ change was made by this reviewer.

## Independence and provenance

`round9_before.json` checks all 190 source/test/C++ files bound by the completed
Round8 review. Every hash matched, and HEAD was
`a23cf1c066d1087571b31733f0577c602040aa8d`. The old manifest was copied intact to
`round8_before_original.json`; Round9 intentionally changes selected source
files and does not rewrite the archived Round8 implementation or outcomes.

This reviewer writes `tests/test_ics_v3_storage_audit.py`, with its own tiny
graph, exact witness schedules and failure expectations. It imports neither
the runtime author's fixtures nor the route author's tests. Root owns storage
contracts/runtime/supply. The routing author owns product-state search. This
reviewer additionally implemented five peripheral compatibility guards at
root's request: request_service.py, partition_observation.py,
distributed_clock.py, joint_reference.py, joint_bundle_reference.py. Those
guards therefore require root review and are not claimed as independently
authored and reviewed by different people. All agents are software agents.

## Observed gaps, not lowered standards

1. Legacy request service's valid-old-route fallback is a separate read-only
   acceptance path. It now invokes the storage committed-witness checker, and
   its dependency digest includes opt-in storage milestones/projected state.
   Ordinary snapshots add no serialization field or hash payload.
2. W2 partition messages do not encode storage progress/release authority.
   Partition observation and DistributedClock now reject storage before any
   run, including a StorageBag hidden in a future generator. Independent joint
   references and their MPC/reactive entry points do the same. A bounded empty
   result is not presented as evidence that those models support EBS.
3. The physical joint transaction already validates every proposal through the
   common owner. A direct bypass witness is independently tested to reject
   without mutation, while a legal full storage witness may commit.
4. Independent attempt_006 exposed two saved-plan holes: a tray physically at
   A with only an S→D plan, and claimed past A→S legs without an actual ingress
   receipt, both produced committed empty supply. Merely finding an S outgoing
   edge in the saved plan is insufficient history evidence. Both failing tests
   and the exact original source bindings are retained.
5. Independent attempt_007 added a third hole: after a real old in-flight S→D
   arrival at tick 8, the legal zero-leg final service ends at 9 and releases at
   11. Altering its unload/usable timestamps to 8 still published supply at 8.
   The check must bind final service timing and current carrier state, including
   zero-leg plans, rather than only compare unload time with EBS departure.

6. The same saved-plan path initially omitted protected final deadlines and
   forbidden waiting at intermediate nodes. Both were accepted as firm supply
   after the ordinary new-route validator had correctly rejected them. Root
   restored the same obligations on saved full plans, including current waiting.
7. A loaded old in-flight trip directly to the final destination could publish
   empty supply without ever visiting mandatory storage. In-flight terminal
   supply now requires actual storage release history; an old trip into EBS
   remains legal and is independently tested.
8. A saved plan whose tray was currently at EBS could infer ingress from the
   node label, whereas a new commit correctly required a real ingress receipt.
   The saved-plan gate now requires the same receipt. Simulation's explicit
   initial-presence/load observation continues to make a legitimate origin-at-
   EBS case runnable.

All seven distinct core counterexamples in items 4–8 were retained and passed
after root's fixes. No passing result was fabricated by deleting a case or
changing a physical deadline/capacity. attempt_015 also confirms the legitimate
zero-dwell, same-tick turnover, origin-at-storage, old-flight, private replacement
projection and checkpoint paths remain runnable.

## Test and bridge evidence so far

- attempt_001: launcher failed before pytest/physics because an imagined test
  filename did not exist. CPU unknown; shell wall 0.6914782 s. The initial
  runner binding scan was subsequently made able to retain a missing-path
  record, and the real filename was used. Failure remains on disk.
- attempt_002: 148 tests passed (40 independent storage cases plus 108 existing
  peripheral regression cases), no source drift. CPU 8.109375 s for the entire
  parent, including nested pytest 7.65625 s. Do not add those two values.
- Direct bridge in attempt_002 runs four ordinary-bag cases in both the frozen
  Round8 source tree and the current tree, with four checkpoint continuations
  per tree. All 100 tick observations, dependency summaries, objectives, state,
  traces and counters per tree agree exactly; only `_ms` timing fields are
  excluded. There are 16 total small physical runs. Child CPU 0.546875 s is
  separate from the parent CPU above. This bridge is narrow, not a substitute
  for the final full regression.
- attempt_003: 42 passed, one test fixture failed admission because the second
  final reception overlapped the first tray's legal hold. Correcting the second
  final arrival from tick 10 to 11 preserves the storage turnover at tick 6.
  CPU 1.390625 s. This is a test-fixture correction, not a runtime fix.
- attempt_004: 43 passed, zero failed; CPU 1.203125 s, no source drift.
- attempt_005: 45 passed, zero failed; CPU 1.125 s, no source drift. Includes
  upstream waiting for the storage calendar and a required route that passes
  the final node before visiting EBS, without premature completion.
- attempt_006: 45 passed, two core failures above; CPU 1.46875 s, no source drift.
- attempt_007: 45 passed, three core failures above; CPU 1.484375 s, no source drift.
- attempt_010: 48 passed, two additional saved-plan failures (protected deadline
  and no-wait dwell); CPU 1.53125 s, no source drift.
- attempt_013: 52 passed, one old-in-flight terminal-supply failure; CPU
  1.46875 s, no source drift.
- attempt_014: 53 passed, one origin-at-EBS saved-plan missing-ingress failure;
  CPU 1.46875 s, no source drift.
- attempt_015: 54 independent storage cases plus nine lifecycle cases,
  **63 passed, zero failed/error/skipped**; CPU 1.578125 s, no source drift.
- attempt_016: pre-routing-fix complete ICS regression, 82 actual files and
  **1118 passed, zero failed/error/skipped**. Parent CPU 71.703125 s includes
  nested pytest 70.75 s; separate bridge child CPU 0.546875 s. All source/test/
  C++ bindings were unchanged. Its full source snapshot is the authoritative
  runtime tree for replaying the four already-imported old window processes.
- attempt_017: 55 independent storage tests passed, CPU 1.203125 s. The new
  private-planning checkpoint counterexample is already rejected immediately
  by the existing restore-time invariant; no redundant core patch was needed.
- attempt_018: after the justified real-query routing repair, **1120 passed,
  zero failed/error/skipped** across all 82 actual matching files. Parent CPU
  71.96875 s includes nested pytest 70.96875 s; separate bridge child CPU
  0.46875 s. All source/test/C++ bindings were unchanged; complete source copied.
  Round8/current direct bridge again agrees exactly across its 16 small runs.

Attempts 008, 009, 011 and 012 were invoked by root using this same metered
runner during implementation/repair. Their stdout/resources and source bindings
are retained alongside the independently invoked runs; root's overall resource
ledger should enumerate every attempt exactly once.

Before-capture CPU 0.078125 s is independent of these runs. Bridge child CPU is
only added once. Initial imports/final writes, ordinary code reading/editing,
messages and the failed launch's CPU were not completely measured; they remain
unknown auxiliary work. A count of passed assertions is not an operational
acceptance criterion.

## Scope retained

The implemented model is fixed, publicly announced, on-carrier storage at a
finite waitable node. It does not implement off-carrier transfer, revocable
release publication, storage machinery, new module permissions or operational
100 ms guarantees. The source business loader is an input-only boundary and
preserves all original/derived bags. A separate explicit runtime adapter is
being reviewed in parallel; neither an adapter nor the tiny lifecycle examples
establishes a completed full-day operating evaluation.

## Real-query tie repair and independent audit

The genuine tick-8876 original-network query for `projected:1x:2` is retained
with its exact state and generator. `plateau_review_001` independently replays
the old and new source, adding a heap assertion that every popped primary f
is the smallest remaining f. Old: 10,000 total work units, 9,317 product pops
all at f=19,749, zero candidates. New: 670 work units, 68 product pops at the
same f, four candidates. Topology/reverse work stays 227/341, horizon 21,600,
K=4 and expansion limit 10,000. The source diff changes only the secondary
heap ordering and diagnostic. Remaining mandatory static travel breaks ties;
it uses no hidden future facts or larger budget.

All four witness geometries, no-wait obligations, final service/deadline,
storage release at 19,500, and complete competing parked-carrier capacities
were independently reconstructed without calling the author's validator.
Ingress is 9,027 or 9,100; final unload is 19,750; storage capacity is one.
Two standalone queries and zero physical simulations consumed 1.25 s CPU;
the heap audit deliberately adds work, so these timings are not performance
benchmarks. K/state-label caps mean altered ordering can alter the candidate
set. A smaller-f plateau caused by unavailable capacity can remain; no global
optimality or completeness is claimed from this repair.

## Window and static-domain evidence

`window_review` audits all four pre-fix window records against the archived
attempt_016 source. Every original 001/002 process correctly reports the live
routing-file drift; this audit preserves that status and treats them as
diagnostic runs. Full source 28,506 → exactly the first arrival hour's 44 IDs,
all raw task fields and censored identities, actual traces, carrier counts,
edge/node capacities and event-derived costs were checked independently.

| Horizon / outer runner | Last tick | Observed / 44 | Completed | Storage ingress |
|---|---:|---:|---:|---:|
| 80 / single tick 001 | 11,430 | 41 | 0 | 0 |
| 80 / chunk 002 | 11,820 | 41 | 0 | 0 |
| 21,600 / single tick 001 | 10,005 | 6 | 0 | 0 |
| 21,600 / chunk 002 | 10,320 | 12 | 0 | 0 |

All four stop on CPU caps. Their differing tick/observed denominators preclude
using J differences as policy comparisons. Two old-source continuation runs
compare chunk checkpoints 11,400→11,430 and 9,600→10,005 with the respective
single-tick final results. Every physical field and counter matches; only
policy `_ms` clocks are excluded. Audit CPU 175.515625 s includes both nested
continuations (16.34375 and 154.5625 s); it is two physical replays, not four
new window deployments. The original audit script is retained with its result.

`static_review_002` independently recomputes integer-tick shortest paths with
Floyd and checks complete-flight necessary domains for all 28,506 bags / 360
groups. All reported domains agree: the original final destination falls
outside the necessary domain for 48 groups / 4,001 bags, on nodes 99, 101, 103,
106, 108 and 110. Sixteen of the 44 first-hour bags cannot reach their original
final destination from storage 53 on the supplied directed graph. This does
not authorize deleting tasks or changing destinations. The domains remain
necessary static bounds, without shared calendars, assignment or physics.
The review covers reachability and rounded-tick distances, not an independent
recalculation of every fraction-second shortest path. CPU 17.421875 s,
zero physical runs. `static_review_001` preserves a reviewer-script key-type
normalization failure (numeric versus serialized string flight key), CPU
0.71875 s; correcting that representation changed no source task or domain.

`post_fix_window_review_001` independently audits both clean-source 003
windows against attempt_018's final source. Both have unchanged before/after
source hashes. Horizon 80 stops at tick 11,760 with 41/44 observed, no ingress
and no completed task. Horizon 21,600 stops at tick 10,080 with 8/44 observed,
one actual storage ingress, no release and no completed task. Node 53's actual
maximum occupancy is one; loaded bag and carrier identity persist during its
hold. Both stop on the original CPU cap, before the last included task is
observed. These are censored implementation/diagnostic observations, not a
completed first-hour workload or evidence of a better policy objective.
The separate tiny lifecycle evidence does complete storage release and
circulation, but must not be substituted for missing original-map completion.
This raw audit uses zero new physical runs and 2.578125 s CPU.

## Closure and next-step constraints

The final source/test/C++ snapshot is `attempt_018/source_snapshot`. Of the
190 Round8-bound files, seven are intentionally changed: runtime.py and
prebalance.py for core storage physics/supply; request_service.py,
partition_observation.py, distributed_clock.py, joint_reference.py and
joint_bundle_reference.py for explicit storage-aware service or unsupported
entry rejection. The other Round8-bound files, all its old tests and C++ remain
unchanged. New modules/tests are separately bound in the final snapshot and
`closure.json`; the old Round8 manifest/source closure remains intact.

There is no unresolved failure among the final 1,120 selected regressions or
these sealed audits. This does not close the operational objective. Subsequent
work still needs to resolve repeated bounded searches and capacity-induced
plateaus without deleting delayed/unreachable bags, distinguish necessary
destination-domain input issues from routing failure, and complete an original
network storage release/circulation window under explicit resources. Any
destination assignment would require a separately declared input decision;
none was performed here. Hold source-clock, task identity, capacity and full
denominator standards. No commit or push was performed by this reviewer.
