# Native027 request computation attribution: current evidence and next boundary

This is a source-only design. It changes no C++, policy, accepted timing ABI,
or frozen evidence. The accepted 027 trace can support a more useful **descriptive
identity partition**, but cannot yet certify that arbitrary other-operation or
`physical_dispatch` work is independent of the measured route request.

The existing finite normal pending-ACK result has a conservative warm bound of
64.3337 ms. Its complete warm envelope already includes diagnostic writing,
native advances and shared work. That finite result does not prove a cold,
fault-general or full-stream 100 ms bound. The slower fault cases cannot be
declared pure-computation violations by counting simulation time or treating
every retained diagnostic write as a required production operation.

## What can be done with the accepted trace, without recompilation

Use the existing closed 027 validator first, then join each native call ordinal
to the actual saved API row and the caller-admitted root interval. Keep the
strict no-straddling root boundaries and exact nested-span conservation. For
each native row, compute `exclusive = duration - sum(immediate child durations)`
once. Resolve the immutable native identity tables and `related_identity` using
the accepted rules, never tray-ID text or a later tray assignment.

An identity partition can use these mutually exclusive labels:

| Label | Sufficient evidence | Charging rule |
| --- | --- | --- |
| Explicit measured operation | Actual submit/query argument is this root's immutable request ID, or a validated command/publication mapping resolves to it | Fully charge |
| Affected business / executor work | Immutable leg relation resolves to the root's observed job, but the row is not linked to the specific route update | Fully charge; do not claim all job work was caused by this update |
| Other identified operation, independence unproved | A different immutable request/job ID exists | Fully charge as potentially shared; identity difference is insufficient for exclusion |
| Proven independent foreign root | Separate actual admission/lifetime, operation linkage, and evidence that this work cannot serve this root or its resources | Separate only if all proofs exist; current original route cohort has no such complete proof |
| Shared or unclassified | No usable identity, mixed candidate set, scheduler/binding remainder, or unresolved dependency | Fully charge |
| Certified physics-only | A measured exclusive code section proved to contain no control/revalidation/publication work | Current 027 broad enum supplies no such exemption |

Thus the initial saved-trace diagnostic should report **zero certified independent
foreign subtraction and zero certified physics subtraction**. It can still show
how much work is explicitly associated with the measured operation, other named
operations and shared/unclassified execution. Its categories must sum exactly
to the same native envelope; they do not replace the existing phase partition
or add to it. A business/operation label and a phase label are two views of the
same exclusive nanoseconds.

All Python request computation remains included: observation filtering,
candidate construction, fallbacks, immutable submit/retry, ACK handling,
mandatory same-timestamp drain, actual request/response encoding, root result
encoding, and unclassified gaps. The current `_step` maximum is only a request
invocation maximum, not the maximum uninterrupted service of all background
executors. Cold startup/setup and whole-campaign sensitivities stay separately
reported in full, without division across roots.

## Why current 027 cannot complete the narrower attribution

The accepted source has useful nested transfer-source and receiver checks in
`circulation_progress`, command/publication mappings, and immutable creation-time
leg relations. However:

1. `request_timing_leg` links a loaded leg to a job, not to an accepted route
   update and its actual preference consumption. Several route updates and the
   normal executor can act on the same leg. It cannot assign all later job work
   to a particular update or prove that other jobs did not consume shared
   capacity needed by it.
2. `control_route` is one `permission_validate` scope covering source identity,
   suffix legality, deadline lower bound, `can_enter`, receipt construction,
   wakeup and command completion. Child ACK/shared-scan spans are conserved,
   but the remainder still combines several required control stages.
3. `dispatch_selected_action` is labelled `physical_dispatch` while it calls
   `can_enter`, checks corridor/destination calendars and faults, commits
   reservations, changes incoming counts, and schedules visibility/events.
   The name does not establish pure physics.
4. Destination merge arbitration is a `permission_validate` scope without an
   individual identity. Candidate scans can serve several jobs. Shared scans,
   owner notifications, queue selection, event-pop/dispatch and binding gaps
   remain relevant to the root even if one event has another job ID.
5. `event_dispatch` has a leg association only for five guarded bag/edge event
   kinds. The raw row has event sequence and logical time, but does not export
   an exhaustive event-kind/control-purpose classification or a proven causal
   dependency set. Load/unload, queue/ranking, timeouts and notification effects
   cannot all be classified from the enum alone.

These are missing evidence boundaries, not a reason to delete their costs.
The saved six-cell phase result is already accepted as a partial conserved
partition; no fresh 025 authority may be substituted for 027 or the 026
pending-ACK experiment.

## Minimal optional instrumentation if the descriptive partition is insufficient

Keep a new version, default-off recorder, fixed capacity, no allocation or clock
reads when disabled, noexcept scope completion, explicit overflow/exception
unknown, and no checkpoint/hash/physical-state fields. Preserve the parent
envelope and add only nested scopes around proven code regions:

1. **Route command execution:** separate source identity/generation/stage checks,
   static suffix/deadline computation, receiver/current-capacity validation,
   preference installation, wakeup/publication and ACK creation. Retain the
   broad outer scope and every remainder. Record a request-to-route/leg link
   only at the actual accepted installation, and a consumption link only when
   the executor actually uses that preference. A stale preference or unchanged
   default route must not acquire a false request link.
2. **Executor commit:** nest current `can_enter` revalidation and calendar/fault
   checks separately from reservation mutation and passive event scheduling.
   Do not relabel the outer `physical_dispatch` remainder as physics. Physics
   classification, if attempted, applies only to a narrowly reviewed mutation
   block whose callbacks cannot perform control work.
3. **Arbitration and event processing:** keep the candidate scan shared, attach
   selected-candidate identity only after selection, and distinguish event
   bookkeeping, actual physical transition, control wakeups/notifications and
   publication delivery with child scopes. A no-action arbitration is still
   control work. Export a diagnostic event-kind tag if it is needed for the
   offline proof, not as an online policy input.
4. **Whole service boundary:** separately measure each complete executor service
   invocation for a maximum continuous-service statistic. Preserve all native
   and Python envelopes, codec and scheduler gaps; sum of exclusive children
   plus parent remainder must remain exact. This does not create a latency
   guarantee from a single small sample.

First compare the new default-off and enabled binary with exact ordered API,
request/retry, physical receipt, complete timestamp and native-seal gates under
the same three fault factors. Test nested exceptions, zero-action events,
shared arbitration, route rejection, stale preference consumption, reused trays,
lost ACK, expiry, recorder overflow, restore/fork and lineage collisions. Only
then may a new saved auditor use the added identities/sections. No compilation
or native run is authorized by this design itself.

## Source anchors inspected

- `cpp/ics_core/runtime/request_timing_recorder.hpp`: numeric phase/method/identity ABI, parent IDs and diagnostic association.
- `cpp/ics_core/runtime/event_driven_junction.hpp`: `request_timing_leg`, `process_event`, `process_destination_merge_arbitration`, `shield_reason`, `dispatch_selected_action`.
- `cpp/ics_core/runtime/circulation_runtime_impl.hpp`: `circulation_progress`, `control_route`, publication delivery, reservation callback and immutable leg creation.
- `cpp/ics_core/runtime/circulation_protocol_commands_impl.hpp`: command wire execution, shared completion scan and ACK delivery.
- `scripts/experiments/g31_ics_circulation/native_request_timing.py`: exact nesting, immutable association resolution and conservative remainder.
- `scripts/experiments/g31_ics_circulation/native027_request_timing.py`: closed accepted ABI and raw-gate authority.
- `scripts/experiments/g31_ics_circulation/route_update_phase_measurement.py`: root/API containment and full envelope conservation.

The adjacent source-bound receipt records hashes and checks the native source
against the archived 027 build. This review performs no additional native replay
and does not rescan the large six-cell raw tapes.
