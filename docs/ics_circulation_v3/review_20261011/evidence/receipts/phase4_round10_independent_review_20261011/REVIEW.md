# Round10 independent storage-search review

2026-10-11. The reviewer owns only the new independent test and this output
directory, and does not modify production routing, runtime or the author's
tests. No commit, push or C++ change.

## Baseline and exact-reference domain

`baseline.json` binds and copies all 201 source/test/C++ files from the final
Round9 attempt_018. Every live hash matched before Round10 changes. The
archived Round9 source is `round9_frozen`; capture CPU 0.453125 seconds,
zero physical runs. Later production changes must be explicit Round10 changes.

The independent oracle in `tests/test_ics_v3_storage_search_audit.py` is an
integer-time search, with each wait advancing one tick and each edge occupying
all its positive integer travel ticks. Its finite horizon, fixed public
release, one decision carrier, calendars and unchanged final destination are
explicit. Exact state identity retains time; no early-arrival dominance is
used across time points. K coverage is separately checked on a small acyclic
three-family instance, where all three paths have the same earliest arrival.

The oracle and independent witness checker call neither production routing,
its reservation views/helpers, nor ExecutionValidator. Real other-carrier
itineraries and old flights are declared in each fixture; their resource
occupancy is separately constructed. Duplicate descriptions are counted once
per physical owner. Final reception covers unload plus hold, and final stock
is checked at every future calendar breakpoint, even beyond the search horizon.
Reaching the final node and then waiting does not move its unload start: a
later service witness requires a real later arrival. Only the subject-under-
test wrapper imports production routing. Common-validator agreement is not
used as the correctness oracle.

Zero-duration passage through a fully occupied waitable storage node has no
node interval in this existing half-open model. It still requires real ingress
and departure and a departure at/after release. Independent manually supplied
witnesses execute this case in whole-route mode and protected next-edge mode.
Unprotected next-edge correctly rejects a prefix that would instead remain at
the full node. This difference is kept explicit rather than treating a full
witness as permission for an unsafe prefix.

## Retained attempts

| Attempt | Source | Passed / failed | CPU seconds | Explicit physical runs |
|---|---|---:|---:|---:|
| 001 | frozen Round9 | 88 / 6 | 1.734375 | 4 |
| 002 | frozen Round9 | 110 / 6 | 1.828125 | 4 |
| 003 | frozen Round9 | 115 / 8 | 1.781250 | 7 |
| 004 | first Round10 candidate | 121 / 2 | 1.656250 | 7 |
| 005 | final frozen Round10 search | 127 / 0 | 1.468750 | 7 |
| 006 | final full ICS suite, 85 actual files | 1300 / 0 | 74.546875 | 7 explicitly counted; suite total unknown |

All attempts save complete source/test snapshots, before/after hashes, stdout
and process CPU. Pytest time is nested, not additive. Oracle/query/witness and
physical-call counters are independent of test pass counts. Attempts 001–004
have no within-run source drift; the same is true for 005–006. Initial interpreter imports, code reading and
editing, shell helpers and receipt writes are not fully metered auxiliary work.

Attempt001 included two mistaken hand expectations that full storage prohibited
zero-dwell transit: one expected arrival111 instead of101, and another expected
no path past a permanently occupied storage slot. Those fixture expectations
were corrected to the half-open model; the original failing test/source remain
retained. This changed no physical deadline/capacity or source workload.

The first Round10 candidate repairs the six original release-arrival misses.
The newly combined downstream-calendar/full-storage counterexample was:

- A→E takes1, E→B takes1, B→C takes2, C→D takes1; B/C forbid waiting.
- E release is3 and another real tray occupies E on [0,6).
- A second real tray occupies B→C on [4,6), with a valid upstream/downstream
  itinerary and no forbidden waiting.
- The exact witness departs A4, enters/leaves E5, reaches B6/C8/D9 and unloads10.
- Projecting only E release3 and its occupied-interval endpoint6 misses E5.
  The first candidate returns D10 if unprotected; with protected deadline10
  it omits this valid witness altogether.

Both variants are retained as failures, reported to root and the routing author.
The final fix projects raw downstream-induced storage departure events as required
storage arrival events upstream, together with public release, charging each
offset/event pair. Both variants pass in 005–006 without changing capacity,
deadline, caller K or budget. This bounded event search has no general
completeness or optimality claim.

## Lower-bound reasoning and completed regression

For a fixed public edge calendar, the earliest full-edge arrival after time t
is nondecreasing in t when waiting is permitted. Therefore time-dependent
Dijkstra with waiting permitted at every node gives an admissible relaxation
of a real suffix after mandatory storage. Ignoring node/reception/no-wait
constraints weakens the bound; it does not authorize a real route. The fixed
suffix floor must not impose another storage visit on a query that already
has actual departed progress elsewhere. Exact physical product-state labels
and K retention remain separate from this relaxed calculation.

Direct capacity-calendar comparisons and a separately time-expanded edge-only
relaxation have also been added, including multi-capacity, duplicate owners,
full-duration edge occupancy, future stock, half-open ties and nonshortest
static exits. The final 127 tests contain 119 integer-oracle calls (8,970 exact
states), 122 production queries, 115 independently checked witnesses, 792
capacity-calendar comparisons and 11 independent relaxed-bound comparisons.
These are domain-specific evidence, not distinct physical deployment counts.

Attempt006 ran every actual `test_ics_circulation_v3*.py` and `test_ics_v3*.py`
file: 1,300 passed, zero failed/errors/skips, with full source snapshots and
unchanged before/after hashes. Parent CPU 74.546875 includes pytest CPU 73.671875;
these must not be added. The Round8 ordinary four-scenario and checkpoint bridge
is exactly equal under both frozen implementations, with separate child CPU
0.531250 and 16 explicitly counted tiny physical runs. The full test suite has
additional uninstrumented physical calls: its exact total is unknown, not seven.

## Read-only evidence audits

`mechanism_review_001` checks 22 main and 44 existing restored raw runs against
saved checkpoints, original task scope and the attempt006 frozen source. It
reconstructs carrier positions, edge/node/reception occupancy, actual storage
milestones, final unload/hold, reuse and objective terms without calling the
production validator or lifecycle reporter. The hand-derived reuse completion
times remain 9/18/24 in both route modes. All pass; CPU 0.218750, zero new physics.
Its script is explicitly an adaptation of the previously reviewed Round9 root
mechanism audit, not a claim of separate original authorship for every line.

Before root ran its window auditor, this review found a schema error: runtime
unfinished counts only observed bags, whereas the full scope also includes
future arrivals. Root corrected it before any execution; there is no failed-run
CPU for that static finding. Both auditors now preserve observed unfinished,
unobserved, and all-44 unfinished separately.

`window_review_001` independently checks both original-budget Round10 windows,
including exact raw first-hour selection, all 44 unchanged destinations,
finite 11-carrier inventory, original source bindings, no future observations,
actual carrier/capacity/release/unload events, costs and query budgets. Passed,
CPU 3.843750, zero new physics. At the CPU stop, h80 has tick11,820, observed41,
completed0, ingress0 and unobserved3. h21600 has tick24,180, observed44, completed18,
ingress18/released18 and unfinished26. Different tick/observed denominators
preclude a direct cost-quality comparison. The additional long-horizon tail
branch, if run, is a separately budgeted development experiment and will be
reported separately below.

`window_review_002` adds exact prefix checks for each window's saved tick10,080
and tick11,760 observations, and independently recomputes their costs from actual
prefix events. Passed, CPU 3.937500, zero new physics. The same-horizon long-window
comparison at10,080 still has zero completion and J879.5 in both Round9 and
Round10; an improved individual query is not yet a matched throughput claim.

`window_review_003` checks the additional h21600 continuation through the declared
tail at28,500. The saved checkpoint24,000 reproduces the original stop24,180 with
every physical-result field exactly equal; all original scope/task/tape/initial
and runtime-contract bytes are retained. Query counts include the correct
checkpoint offset, and the original trace is an exact continuation prefix.
Actual edge/node/reception capacities, final service, milestones and costs pass
again. CPU 1.171875, zero new audit physics. At28,500 there are still18 completed,
18 ingress/departures,26 unfinished and no in-transit carrier. This is a completed
tail observation, not a drained business workload; its extra physical budget
does not change the original600-CPU result.

`projection_boundary_001` reconstructs the original 28,506-task source workload
and probes a 127-task same-flight destination mutation. The stale content seal
is rejected, and resealing the payload still fails with the unchanged external
projection declaration. Replacing both the workload and its declaration can
pass the binding gate, which replaces the input trust root. The pure API trusts
an already audited Workload; it does not reread raw files or provide an authority
signature. This probe does not claim the modified full projection is valid and
creates no runtime input. CPU 9.687500, zero simulation and zero full-projection
calls. Root's separate raw-source audit of the real full artifacts is required
evidence for those artifacts; a future runtime adapter must reverify source and
projection inputs explicitly.

## Review conclusion and scope

No unresolved violation was found within the declared tiny exact domains, source
freeze, ordinary behavior bridge or the audited mechanism/window trajectories.
The independently discovered late-ingress omission is repaired and the failing
pre-fix evidence retained. No production source was edited by this Round10
reviewer. Bounded search can still omit routes outside those domains; finite
budget exhaustion does not prove infeasibility. The raw original workload remains
44 tasks, including its unreachable destinations, with all unfinished tasks
retained. Search repair and successful lifecycle evidence do not establish the
user's full operational or research-quality target.

`closure_001` records the exact final source delta from all201 archived Round9
files, preserves the Round9 archive, and binds this review's evidence. Known
CPU receipts include failed attempts and all repeated reads; unmetered editing,
manual review, shell helpers and uninstrumented full-test physical calls remain
explicitly unknown. No commit or push was made.
