# Round11 independent projection-runtime and terminal-screen review

2026-10-11. Reviewer owns only the two new independent tests and this output tree.
No production edits, commits, push or C++ changes. The requested research and
operational targets remain open; test counts do not establish those targets.

## Source and independent fixture

`baseline.json` reads and copies all 206 files bound by the final Round10 closure.
Every source/test/C++ byte matched, as did HEAD
`a23cf1c066d1087571b31733f0577c602040aa8d`. The original Round10 source is retained
in `round10_frozen`. CPU 0.328125 seconds; zero physical calls.

The new independent test imports no author fixtures. It constructs a complete
two-parent-flight timetable with one early and one direct bag per family, then
the complete 2x derived families: eight bags and twelve old segments. Raw,
parent, canonical segments, normalized tasks, manifests and the six-node graph
are all explicit. Storage cannot reach original sink2, but reaches sinks3/4
with a return to loader5. A second parent's legal original sink3 is retained.
The original loader0 is not silently reconnected by a closed edge. The fixture
also includes mixed protection, two finite trays, exact decimal clock values
on either side of tick boundaries, fixed release and nonzero unload/hold.

All non-destination runtime fields are compared with the original runtime
tape, including StorageBag type/contract. The originals and full parent groups
remain intact. Hand-derived first-bag clocks are arrival2, storage ingress4,
release251, final arrival252 or253, unload completion254 or255, and usable empty
after two additional hold ticks. One live run and one checkpoint restoration
match every physical-result field, excluding only policy timing measurements.

## Active resealing and input-boundary probes

The probes modify both the original object and content seal, the projection,
the external source declaration, and the run SHA. The unchanged raw/canonical
source still rejects altered deadline, protection, destination, arrival,
publication, release and old segments. Updating a projection's own seal and
run SHA also cannot remove a derived member, split a family, change its declared
rank winner, forge its necessary domain or instance count, duplicate/reorder
records, or replace original provenance.

Each original source input is mandatory. Rebinding the normalization manifest
does not excuse missing normalized bags, bad canonical stages or false totals.
A raw file changed after projection validation is rejected by the exit rehash.
All six fixed run bindings are checked, and a valid newly declared projection
is rejected by the old fixed run contract. The external projection declaration
is used independently of the embedded declaration. Runtime unload seconds must
match exactly, including differing values that round to the same two ticks.

Full source and projection provenance stay on the environment side. Initial
state contains no future identities or milestones. Observations, generator
objects and restored policy arguments contain only actual observed tasks;
remaining arrivals stay in the checkpoint's private tape. The test checks a
real in-flight checkpoint before physical storage ingress, then replays through
actual release, final unload and hold.

Replacing every external declaration and the actual raw files is a new input
version, not a signature bypass over the previously frozen experiment. SHA
integrity is not an authorization system. The new runtime boundary does reread
the complete source, unlike the intentionally narrower pure projection API.

## Retained runs and resources

| Attempt | Scope | Outcome | Parent CPU seconds | Explicit physical calls |
|---|---|---|---:|---:|
| 001 | selected fixture node; runner startup | failed before pytest | unknown | 0 |
| 002 | independent projection-runtime audit | 55 passed, zero failed/skipped/errors | 4.250000 | 2 |
| 003 | all 87 actual ICS test files | 1,399 passed, zero failed/skipped/errors | 88.875000 | 2 newly instrumented; full total unknown |

Attempt001 exposed an instrument bug: the runner treated `file.py::test_name`
as a filesystem path while hashing inputs. It failed before pytest or physics.
Its exact runner and fixture are retained, along with the tool's 0.6572895-second
wall observation. Process CPU and wall were not captured and remain unknown.
The runner now separates the file portion from pytest selection syntax.

Attempts002/003 retain source snapshots, all test outcomes, stdout/stderr and
before/after hashes, with no within-run source drift. Attempt002 has54 adapter
calls. Pytest CPU 3.609375/87.796875 is nested in parent CPU, not additive.
The full suite's uninstrumented physical calls are unknown, not zero or two.

Attempt003 also runs the original Round8 four-scenario/checkpoint ordinary-bag
bridge. All physical fields match exactly. Independent child CPU 0.578125 and
16 tiny physical calls are additional to parent CPU. Full regression was run
only after production and both new tests were frozen; it is not repeated without
a new correctness reason.

`full_adapter_review_001` passes a read-only audit of all85,518 adapted records
across1x/2x. It uses no production loader/adapter/projection import. Original
task/group records match the sealed Round10 artifacts, while original raw text
is independently parsed with Fraction to recompute arrival/release/deadline,
protection and the entire runtime Bag. Complete denominators28,506/57,012,
segments43,603/87,206, changed finals4,001/8,002 and360 full parent groups agree.
CPU10.000000 seconds, wall10.364494, zero physics and zero adapter calls.
The artifact comparison overlaps the root's separate full-tape audit; the
direct raw clock recalculation is additional evidence, not a new independent
sample, operating day or physical experiment.

## Original four-cell window evidence

The root's pre-run four-cell protocol is original/projected × horizon80/21600,
with the complete first exact source hour of44 bags,11 finite trays, actual K1,
10,000 logical query budget,600 physical CPU/900 wall cap and tail28,500.
The complete28,506-task source and predeclared Round10 projection are validated
before selecting the window. Only the projected cell changes declared final
destinations. Projection construction/validation costs remain in parent CPU;
the physical interval is nested and separately identified.

Static review found no execution blocker in the runner. It supplies only the
initial state, private selected tape and ordinary simulation parameters to the
engine. Full projection/source metadata remains outside policy arguments.
The independent raw auditor is prepared to check unchanged original fields,
the complete frozen parent-group mapping, actual event/capacity/service/cost,
future separation in saved checkpoints, matched trace prefixes, and strict
Round10 physical equality for the original cell at common ticks. No completed
window or throughput result was claimed before those sealed outputs were audited.

`window_review_003` now independently passes all four sealed original cells,
using the original attempt003 frozen source rather than the later screen source.
Every source hash remains unchanged. The complete44-task tape and all11 trays
are retained; every actual event, node/edge/reception capacity, storage milestone,
release, final unload/hold, cost term and checkpoint private future tape is checked.

| Original cell | Last tick | Observed / complete44 | Completed | Actual storage ingress / release |
|---|---:|---:|---:|---:|
| original h80 | 11760 | 41 / 44 | 0 | 0 / 0 |
| original h21600 | 23880 | 44 / 44 | 18 | 18 / 18 |
| projected h80 | 11760 | 41 / 44 | 0 | 0 / 0 |
| projected h21600 | 11640 | 41 / 44 | 0 | 1 / 0 |

All four exited on their original CPU cap. The projected tape changes16 final
destinations within the complete44-task window, according to the fixed full
parent-family projection. Different stopping ticks and changed OD do not support
an algorithmic quality improvement claim. Original-cell common10080/11760
physical results match the corresponding Round10 result exactly.

The raw-audit attempts001/002 failed only because the new checkpoint comparison
mistakenly expected checkpoint.trace to equal result.trace. First normalizing
tuple/list did not fix it. Reading the runtime confirmed that result() adds one
presentation-only current-tick marker while checkpoint stores the executable
cursor trace. The fixed assertion appends exactly that one marker, preserving
every recorded event and its order. Both failed scripts/results remain retained:
CPU0.312500/0.296875 seconds, zero physics. Attempt003 passes with CPU6.687500,
zero physics; no replay was needed.

## Adaptive terminal-screen audit

After the original four cells sealed, the author added one opt-in storage-aware
terminal-screen module. Every complete witness reserves its final node from
arrival to INFINITY and must arrive by now+H. Therefore a full-capacity peer
conflict anywhere in [now+H, INFINITY) rules out the current query's complete
witness. This is a sufficient current-calendar certificate, not permanent task
infeasibility. Future dispatch or a legal calendar change requires a fresh check.
Intermediate storage capacity is not used as a terminal rejection: full storage
can still permit zero-dwell passage at the announced release.

The independent new test reuses the earlier independently authored integer
calendar fixture, without author-test imports. A separate finite one-tick wait /
positive-integer edge traversal oracle covers ordinary, storage and empty routes.
It checks final stock beyond the query horizon and service/protection constraints
without production routing, effective-reservation or validator calls. Sixty-seven
explicit oracle calls visit1256 exact states; this is a defined tiny domain, not
a general completeness proof or67 physical experiments.

The audit checks half-open endpoints, future occupancy after the horizon,
zero/multiple capacity, duplicate descriptions of the same carrier, old transit,
query-carrier exclusion, zero-dwell storage, invalid contract/progress/request
delegation, and complete candidate tuples. Every search-budget cutoff in the
chosen small fixture is compared cold versus warm after a certified skip; later
calendar and graph changes are re-queried. Screen work remains additional to the
unchanged inner budget. Streaming rows preserves cumulative totals. The wrapper
survives Simulation's automatic storage wrapping, checkpoint and explicit cache
restore, and pure factories create separate ledgers/caches. Slow, unknown, nested
or ordinary-only installation paths fail without partial mutation.

Attempt004 found one real API transparency bug: implicit K was4 in the wrapper
but3 in its StorageCandidateGenerator delegate. Four legal path families produced
an extra complete candidate. The author changed only the new wrapper's default
to3, preserving explicit runtime K1. The actual failing source and result remain.
The second failure was in the independent test, which compared generation_ms
wall timings during otherwise equal restored physics. The correction excludes
only policy fields ending `_ms`, retaining all physical fields and policy counts.
Attempt004 had86 passed/2 failed, CPU1.687500, two tiny physical calls. Expanded
attempt005 passes96 tests, CPU1.421875, two tiny physical calls, no source drift.

The final production freeze justified exactly one additional full regression:
attempt006 covers all89 actual ICS test files and passes1519 tests with zero
failures, skips or errors. Parent CPU80.890625 includes pytest79.968750; separate
Round8 ordinary-bridge children consume0.515625 and16 physical calls, all exact.
Four physical calls in the two owned independent audits are instrumented; the
rest of the full suite remains an unknown physical count. The original1399-test
freeze and its bridge remain separate evidence, not overwritten.

The new adaptive projected+h21600 screen deployment follows a separate declared
protocol and records every certificate's complete public snapshot, query ID and
SHA. Its additional work, observation/serialization CPU and original fixed caps
are explicit. The deployment has now sealed without source drift at tick19620
on its original CPU cap: all44 tasks observed, zero completed, seven actual
storage ingress events and six releases. It has18,354 queries. The independent
`screen_window_review_001` passes the complete44-task raw physical audit using
attempt006 frozen source, CPU1.093750 seconds and zero physics. All remaining
tasks remain present.

`certificate_review_001` independently passes every18,317 certificate among
18,354 queries. The auditor imports no production code. Each query ID and SHA
binds the exact saved public state. Prior complete candidate options plus actual
commit trace reconstruct every active edge, waiting-node and final-service/stock
reservation. Idle stock is checked against actual arrivals; old-flight occupancy
is reconstructed separately. The reconstructed calendar equals the public
calendar before any certificate is evaluated. The auditor then counts distinct
other carriers on half-open intervals, checks the earliest sufficient conflict
at/after now+H, and compares the claimed witness slots with those real bookings.

All certificates concern node47. The first is query38 at tick10434: trays
proxy-initial-0/24/49/95 already have actual committed future terminal stock
occupying its four slots. The subsequent certificates are repeated query-local
observations of this declared condition, not18,317 independent scenarios.
Every storage milestone in these public states matches an actual ingress/release
event. The full public task census contains exactly the tasks observed by each
query time, and original bag fields remain intact.

Summed screen work6,074,458, screen CPU9.453125 and snapshot-observation
CPU176.187500 exactly match the deployment ledger. These CPU intervals are
nested in the original physical interval, not additive experiment runs. The
read-only independent certificate audit costs91.468750 CPU /93.644150 wall
seconds, with zero new routing queries or physical calls. It does not sample
the snapshots. The audit also verifies all physical-result fields exactly at
common ticks10080 and11640 against the original unscreened projected cell.

The screen deployment used parent CPU654.921875, with602.718750 nested physical
CPU and the declared chunk-boundary cap check. This includes the additional
recording/serialization work. Reaching a later tick while preserving the common
prefix is useful implementation evidence, but the zero completed tasks and CPU
censor remain explicit. No speedup ratio, equal-total-work claim, completed
operating window, independent-day result, throughput target or100ms acceptance
is established. Static reachability of projected destinations also does not
guarantee joint capacity feasibility or eventual service under this policy.

## Evidence closure and remaining scope

`closure_001` binds the final attempt006 source, tests and C++ against the original
Round10 baseline. The expected closure is206 existing files unchanged and six
new files: projection-runtime production/author/independent tests plus terminal-
screen production/author/independent tests. The original209-file attempt003
freeze is retained for its1399-test regression and the four original windows.
The closure receipt records the actual file count, HEAD, C++ hash and drift test.

All metered failure attempts, source snapshots, stdout/stderr and read-only
audits remain available. The known CPU subtotal is a sum of individual receipts
plus the separate ordinary-bridge children; it is not additional CPU to add again.
Attempt001 startup CPU is unknown. Unmetered reading/editing/shell overhead and
physical calls outside the two instrumented audit modules in full pytest remain
unknown, rather than zero. The44 explicit independent physical calls include
32 bridge branches and12 tiny test calls; the root's five deployments belong to
their separate receipts. Test/oracle/check counts are not substituted for
business behavior. No production source, existing tests, C++ or Git history was
changed by this reviewer during Round11; no commit or push was performed.
