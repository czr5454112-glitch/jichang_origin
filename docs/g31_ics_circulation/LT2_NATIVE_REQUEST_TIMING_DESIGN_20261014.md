# Native request timing: diagnostic implementation and pending acceptance

Status: reviewed implementation and native022 build-only passed,
2026-10-14. Native acceptance tests and measurement have not executed. Native021 and the corrected bundle002 evidence remain
unchanged. This document implements the interpretation work for the attached
LT2 plan §9.1; it does not declare the 100 ms requirement satisfied.

## What the existing evidence does and does not show

The corrected
[bundle002 manifest](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_bundles_full1x_5000_002/manifest.json)
captures 5,000 owner updates over the complete 28,506-job input, ending at logical
time 12,249.63798600003 with its declared activation budget exhausted. There are
1,186 immutable protocol IDs, 1,368 attempts, 3,818 no-new-message updates and ten
open message roots. The inner owner maximum is 66.445 ms and the outer owner
maximum is 67.1134 ms. Those are not complete per-business-request measurements.

The largest closed coarse bound is 3,860.75 ms: 3,069.9032 ms owner activations,
445.674 ms scheduler gaps, 239.8241 ms whole native calls and 105.3487 ms output.
All of these are retained in the reference ledger. Native time includes
simulation, and old requests currently inherit every subsequent same-owner
activation until terminal ACK. Neither a bound above 100 ms nor the owner
maximum alone establishes the complete request result.

There are two distinct kinds of dependency. A new independently triggered update
B can read reservation A as an input without becoming work needed to complete A.
By contrast, A's transport retry, terminal-result handling, cancellation,
fallback, and explicit replacement/replanning remain A's continuation. Reading
an ID is not a sufficient test for either classification. In particular,
`transfer_candidates` reads pending transfers to prevent duplicate promises and
reserve supply. Removing all such policy work based only on unchanged ACKs was
rejected. No read-proxy discount has been implemented.

## Business root and continuation contract

1. Accept a root before reading/observing its business update. Record the
   immutable business update ID, its actual trigger and scope, owner, and affected
   job/tray IDs. The existing controller exposes owner activations, not an
   external per-job business request interface; those roots remain explicitly
   `owner_activation_updates`. Do not rename them into per-job requests.
2. An immutable native protocol ID has one creating root and may have additional
   explicit parent roots for a joint operation. Transport retries reuse that ID
   and root. Batch creation cost is charged in full to every explicitly dependent
   root, with no division by number of selected jobs or messages.
3. A separately offered update receives a new root even if it reads an existing
   reservation. A child created to resolve an old result, cancellation, lease
   failure, replacement or fallback must carry the old root through an explicit
   lineage record. A mixed activation can have both an independent root and old
   parents; its inseparable shared preparation/solve is fully charged to each.
4. Current policy `current.published`, `active_routes`, `forecasts` and cooldown
   transitions provide possible exact references, but do not currently emit a
   complete business parent graph. A new ID alone is not evidence of independence.
   Until all creation paths are classified, report both the unchanged coarse
   upper bound and a partial measured phase decomposition; do not issue a
   complete refined total.
5. Completion includes the delivered outcome, its required client processing,
   any child continuation and the actual mandatory same-timestamp drain and
   returned output. No-action and immediate-rejection roots remain in the
   denominator. Unknown, lost-ACK, runtime-error and censored roots cannot close
   from an offline physical result.

The first native experiment should supply the missing phase evidence while
leaving this coarse parent attribution intact. Separating later independent
policy roots is a subsequent explicit controller lineage task, not a native
stopwatch's inference.

Implemented files are the standalone [recorder](../../cpp/ics_core/runtime/request_timing_recorder.hpp),
native runtime/binding hooks, [offline call wrapper](../../scripts/experiments/g31_ics_circulation/capture_native_request_timing.py),
and [partition validator](../../scripts/experiments/g31_ics_circulation/native_request_timing.py).
The separate [capture driver](../../scripts/experiments/g31_ics_circulation/profile_native_request_timing.py)
adds these diagnostics to the unchanged bundle ledger, preserving the full native
charge and the complete original input and controller budgets. It checks the
binary against an accepted clean-build receipt and exact compiled source hashes,
preserves recent-policy capability and exports only after measured return/output.
The validator requires exact native/Python outer-call correspondence, consistent
numeric identity tables, immutable leg associations and exclusive nesting. It
always emits zero physics subtraction and no refined per-request totals. Missing
identities, clock/coverage inconsistencies and diagnostic invalid flags return
unknown. It currently supports one session/epoch per audit; restore/fork traces
cannot be silently joined.

The standalone MSVC `/std:c++17 /W4 /WX /O2` test passed twelve cases (assertions
enabled), including zero scope allocations, stale token reuse after export and
idempotent early phase closure:
[log](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_native_recorder_001/test_005.log).
Thirty-four pure Python validator/proxy/driver tests passed:
[XML](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_native_timing_tests_005.xml).
The combined existing accounting and sidecar suite passed all 88 cases:
[regression XML](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_accounting_tests_011.xml).
Sixteen native tests have been authored and collected, but not executed:
[tests](../../tests/test_g31_circulation_native_request_timing_runtime.py).
The new native022 binary compiled successfully; this does not yet establish
physical equivalence, complete stage coverage, or measured performance.

## Diagnostic API and storage

The implemented private runtime component is a default-disabled, fixed-capacity
`RequestTimingRecorder`, owned outside `CirculationState`, runtime configuration,
`StateCheckpoint`, state seals, physical events and policy observations. A new
header has standalone tests independent of circulation simulation.

The binding exposes only explicitly offline methods:

* `offline_request_timing_start(capacity, session_identity)` prepares a fresh trace epoch at a safe
  outer boundary. Allocation is allowed here, before measured requests.
* `offline_request_timing_take()` returns and clears completed records after an
  outer call. Copying/JSON export is diagnostic work measured separately. It must
  never drain a running span, expose a future event to the policy or influence
  native/policy decisions. The ordinary controller proxy does not forward it.
* `offline_request_timing_stop()` disables capture at a safe boundary. Unknown
  capture gaps remain recorded; disabling it is not permission to certify them.

Each batch exports a cumulative `emitted_span_count`. The validator requires
exactly the next contiguous span IDs in original emission order, including the
final leaf. Missing/reordered exported records cannot be silently absorbed into
a parent's exclusive remainder. This detects lost records; it cannot prove that
a source path lacking a hook was instrumented. Source review and native path
coverage tests supply that separate check.

Each numeric span row carries trace epoch, call ordinal, span ID, parent span ID,
monotonic start/end offsets, phase enum, association kind/index, attempt, current
event sequence where relevant, outcome/error flag and logical event time. Numeric
associations distinguish transfer index, protocol command index, physical leg
index, job index and shared scan. Stable string IDs are rendered later using an
offline identity table; they must not be copied or allocated in a commit hook.
The table links command native_index to publication/route index and transfer
index to its immutable public request ID. IDs are not reconstructed from receipt
text or current tray.transfer after that field has been cleared.
Synchronous rejections before a native table row exists use a binding-submission
association, resolved against the captured payload by session identity, trace
epoch and outer call ordinal. They never use a guessed transfer/command index.

The span guard is noncopyable RAII. Its constructor/destructor and recorder
append path are `noexcept`, use only preallocated trivial rows, and never call
Python or a user callback. A full buffer, invalid nesting, unsupported identity,
clock anomaly or missing final row sets a sticky invalid/overflow flag. Physical
execution continues unchanged; that trace reports unknown. No silent eviction,
sampling, overwrite or allocation fallback is permitted. A depth limit is also
explicit and fail closed. Disabled mode performs no clock reads.

`restore` resets/disables the target instance's diagnostics. `fork` creates a
disabled child with a distinct session namespace and leaves the source trace
untouched. Neither target inherits elapsed clocks or open spans from another
instance. The capture requires an explicit nonzero uint64 session identity and
checks the native returned namespace. The driver uses one campaign-local
allocator retaining actual object identities: distinct instances receive distinct
namespaces and the same object retains its namespace. Independently authored
callers must use one allocator or equivalent campaign-unique identities; the
analyzer cannot infer object identity from fabricated metadata. Epoch counters alone do not
distinguish forks. Restart is rejected while unread records remain. Restore
retains unread rows with a sticky invalid/reset flag for offline export; a new
epoch must be explicitly started after export.
Restoring an active measured campaign requires explicit offline linkage to the
prior trace and its pending IDs. A native checkpoint hash remains identical with
capture enabled/disabled. The trace epoch is not part of the physical hash.

## Outer-call coverage and clocks

Python records its complete native call envelope, including pybind conversions.
C++ records one nested outer span at each relevant binding entrypoint, with an
ordinal and method enum. Do not assume the Python and C++ clock epochs match.
Use C++ relative intervals for exclusive native partitioning and compare their
duration to the containing Python interval. The Python-envelope remainder stays
charged in full; a negative remainder or unexpected call ordinal is unknown.
Never subtract a median clock/read overhead from recorded request time.

Record complete call envelopes for submit, request/command query, every observe
endpoint (including native021 recent), demand signature, advance, and result
construction. `result_at` itself calls advance_to: nested spans must exclude that
child once, not count it twice. Existing owner outer intervals already include
observe/query/submit native work, so those nested spans provide a breakdown and
must not be added to the owner total again.
The inventory also includes `protocol_planning_snapshots`, whose delivered
message selection and rendering is real observation work when requested.

Each native advance keeps its original full bound. Its measured inner spans can
initially report identified control work and unclassified remainder. Only a
reviewed event/phase coverage map may classify a piece as physics-only; a
function name or the presence of a physical event is insufficient. Generic
event dispatch, notification generation, shared scans, fallback/route selection
and scheduler remainder are conservatively charged until classified. Shared
control work is charged whole to all dependent IDs, never averaged.

## Required source hooks

Paths below identify hooks added after frozen native021. Initial source placement
is reviewed and native022 compiles; runtime coverage acceptance remains pending.

| Location | Required coverage and attribution |
| --- | --- |
| [binding submit/query/observe](../../cpp/ics_core/bindings/circulation_session_binding.hpp) | Start the outer envelope before payload decoding and owner checks. Include synchronous rejections, duplicate identity comparisons, return rendering and all observation serialization. Link every submitted attempt, including rejected attempts that allocate no native request row. |
| [submit_circulation_protocol_transfer / command](../../cpp/ics_core/runtime/circulation_protocol_impl.hpp), [command implementation](../../cpp/ics_core/runtime/circulation_protocol_commands_impl.hpp) | Admission and immutable-retry validation, namespace/owner checks, local visibility, schedule creation and dedup scans. A duplicate retry is an attempt, not a new root. |
| `process_circulation_protocol_event`: protocol_resend / timeout / ACK and owner recovery | Exact request/attempt processing, ACK drop/duplicate handling, notification and retry scheduling. Recovery scans are shared work; retain the complete scan until exact affected-set attribution is recorded. |
| `process_circulation_protocol_command_event`: command_wire / timeout / ACK | Source execution/revalidation, publication capture, cancellation/withdrawal reference resolution, pending and terminal ACK scheduling. Publication source capture is control computation, including planning_snapshot. |
| [circulation_progress](../../cpp/ics_core/runtime/circulation_runtime_impl.hpp) | Outer shared scan plus each transfer iteration, including early continue/rejection. Source checks: availability, lease, tray readiness/location, export permission and min stock. Receiver checks: zone, receive permission and actual capacity. Reservation commit: reception_node, transfer association, mode/status, receipt and leg creation. These run on load/release/recovery/resource events as well as original module_message. A wire-only timer misses them. |
| `process_circulation_event`: module_message | Actual delivered request processing and lookup, deferral during owner outage, duplicate ACK and shared circulation_progress children. |
| `process_circulation_event`: control_route | Actual delivered route permission, generation/traversal/prefix, job identity, suffix permission, necessary deadline/fault/capacity checks, status update, resource wakeup and final ACK. `submit_circulation_route` only enqueues; timing it alone does not measure revalidation. |
| `process_circulation_event`: control_demand / service_forecast / planning_snapshot | Recipient availability check, capture delivery/expiry status, command completion and owner notification. Include dropped/delayed/duplicate outcomes in the attempt ledger. |
| `transfer_wakeup` / `transfer_expiry`, cancel and recovery | Deferred permission checks, rollback/release, failed leg and subsequent required continuation. An expiry of a departure lease does not automatically terminate a departed transfer. |
| [shield_reason / destination-merge validation / dispatch_selected_edge](../../cpp/ics_core/runtime/event_driven_junction.hpp) | Current physical permission, capacity, fault and destination calendar checks are executor control work even when called by a physical event. First cover the entire executor decision/commit envelope; do not subtract route selection as simulation. |
| `publish_prepared_event` / `publish_prepared_reserved_event` → `circulation_publish_event` → [reserve_enter](../../cpp/ics_core/runtime/circulation.hpp) | Actual irreversible receiving/edge commitment happens here, before the scheduled EdgeEnter event. `reserve_enter` explicitly permits no allocation, callbacks or exceptions. Place the trivial span guard outside it, using precomputed numeric identity and preallocated storage. Cover both publication paths, staged commit/rollback and no-throw paths. |
| `circulation_leg_completed` / `circulation_leg_failed` / edge enter/exit | Physical trajectory work must be distinguished from transfer completion bookkeeping, receiving-lease release and request outcome updates. Capture transfer identity before tray.transfer is reset. Continue counting ACK retrieval and retries until the client sees a terminal result. |
| `process_one_event` and `advance_circulation_until_owner_notification` | Exact outer event envelopes plus remaining queue/dispatch/notification/timestamp-completion overhead. Record attempted/processed event counters and complete timestamp flag. Native event-budget cuts remain partial; no root closes on an incomplete timestamp. |

`CirculationState::can_enter` is also used on projected state by transaction
validation. Instrumenting the data object itself would mix speculative and real
execution and contaminate copied state. Prefer runtime call sites with an
explicit `actual_executor` versus `speculative_validation` phase and identity.
Speculative validation is still computation when performed for the request.

## Minimum acceptance experiment

Before performance conclusions, require these tests and evidence:

1. Pure recorder tests: disabled behavior, nested exclusive conservation,
   exception exit, overflow/depth failure, duplicate/missing end, call ordinal,
   reset/fork/restore identity and no allocation in scope entry/exit after start.
2. Native semantic pairs on the same input/checkpoint: capture off versus on,
   exact ordered public projections, submitted payloads/retries, ACKs, event
   boundaries, receipts, returned state, checkpoint seal and result. Include
   immediate rejection, source/receiver rejection, future-departure wakeup,
   unavailable owner/recovery, lost/duplicate ACK, expiry, cancellation,
   multi-owner shared progress, route rejection, and staged physical commit.
3. Verify every successful transfer has source and receiver validation plus the
   actual reservation/dispatch trace; every terminal outcome has delivered ACK
   and client processing or an explicit synchronous rejection. Rejected-before-
   receiver requests record that receiver validation was not applicable, not
   a fabricated zero-duration completed receiver stage.
4. Verify total native intervals partition into measured exclusive children and
   retained remainder. Missing exported spans/calls/identities, invalid flags and
   inconsistent counters must produce unknown. A required hook that never emits
   needs a separate path-coverage test; conservation alone cannot detect it.
   ACK create/delivery phases include drop/duplicate handling and are not evidence
   of successful client delivery. The original full-native bound is emitted beside
   the finer partition. No unknown piece is silently classified as physics.
5. On the complete original 1× input, run the fixed 5,000-update prefix using the
   frozen input/config/budgets and raw segment output, followed by serial
   uninstrumented replay. Report instrumentation overhead, all no-action and
   failed/update denominators, open roots and logical waits. A result remains
   prefix-scoped. Only after this succeeds use a predeclared full-horizon run and
   required load/hardware cases; no smaller offered population substitutes for it.

The ten open bundle002 roots cannot all close with a free final drain. Eight are
transfers (including one earliest departure at 20,679.542) and two are recent
publication commands; their terminal ACKs are not yet available at the saved
cutoff. The 5,000-update budget is spent. An additional completion extension must
retain the original prefix result, declare its extra horizon/activation budget
and report a separate scope. No extension or root deletion has been applied.

## Build and execution status

Native022 was built into its own directory with a single compile worker. The
[build-only receipt](../../outputs/experiments/g31_ics_lt2_sustained_20261014/native022_build_only_001/receipt.json)
records exit 0, 68.586 seconds, unchanged source, exact source archive and binary
SHA256 `453941d16e500225625b78a2d8594cb7d7143a6b12ade9e64600dbddb2ae370d`.
It explicitly records no CTest and no NativeSession execution. The measurement
driver rejects this build-only receipt until a separate accepted clean-build
receipt records the required native acceptance tests.

The running native021 binary and archive remain unchanged. The standalone
recorder compile/test lasted 6.47 seconds and the native022 build ran concurrently
with the parent's full-input native021 run; their start/end and workload are
recorded in its background-work evidence. That full-run wall time is not an
isolated performance benchmark.

The [ready receipt](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_native_timing_ready_001/ready.json)
freezes reviewed sources and exact native-test and measurement commands. After
the slot release, [native acceptance](../../outputs/experiments/g31_ics_lt2_sustained_20261014/native022_acceptance_001/independent_validation.json)
passed all 16 runtime cases. Separate serial native021-off, native022-off and
native022-on processes produced identical ordered public observations, controller
outputs, calls, native boundaries and native/checkpoint seals for the complete
lost-ACK H20 case (217 activations, 374 boundaries, 67 submissions) and a
500-activation prefix of the unchanged 28,506-job original input (829 boundaries,
61 submissions, cutoff 8,993.851872). Each prefix used multiple controller calls,
so equality includes saved continuation. Both saved timing traces were read again
and validated independently. All 65 compiled source hashes and both native022
binaries were unchanged. A newly added, unincluded SHA header is explicitly
excluded from the compiled archive.

Two unsuccessful test attempts remain saved: the first stopped at sandbox binary
access before simulation; the second passed ten cases and failed six test-only
comparisons of distinct checkpoint wrapper objects. Comparing their actual
checkpoint state hashes corrected that assertion; no C++ change was needed.
CTest and the 5,000-update measurement remain unexecuted. The short comparison is
a semantic and partial-stage acceptance check, with no isolated speed claim.
The proposed bounded experiment retains 28,506 offered jobs, horizon 86,400,
5,000 activations, 500-activation shards, event budget 100,000 and serial
uninstrumented replay. Evidence export and diagnostic storage are separate;
retained diagnostic objects may affect memory/GC overhead inside measured windows.
No identified phase partition supplies a complete per-business-request bound
without the missing explicit policy continuation graph.
