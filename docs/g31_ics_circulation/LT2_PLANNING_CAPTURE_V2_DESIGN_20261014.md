# Planning capture v2: minimal later-decision information contract

Status: implemented in compiled native025 and passed focused native acceptance
and old-contract parity. The online rolling experiment is still unexecuted.
Existing v1 capture, digest, adapter, native020 evidence and later conditional
model remain unchanged.

## Why it is feasible in the current native implementation

`circulation_runtime_impl.hpp` writes an immutable `UNLOAD_COMPLETE` receipt at
the destination when the job becomes completed. It records the job, tray,
destination node and physical time, and notifies that node's owner. The receipt
survives `HOLD_COMPLETE`, which clears the tray's current job. Therefore a new
capture can filter existing native receipts by event and destination ownership;
it need not expose the global job-state table or infer completion from absence.
It must not expose the receipt's global traversal/runtime indices.

The existing protocol request and command records already contain immutable
submitted identities and last **delivered** ACK references. Those support a
capture of source-owned submitted physical actions. The hidden execution status,
result status, pending wire events and remote physical transfer table are not
substitutes for delivered ACKs. A physically completed command whose ACK was
lost remains unresolved in this contract.

## Versioned wire boundary

Add `planning_snapshot_v2` and a separate
`protocol_planning_snapshots_v2(owner)` endpoint. Keep the v1 parser, field set,
digest and output unchanged. Reuse its command wire delay, publication delay,
owner/recipient fault suspension, immutable capture, retry identity, expiry,
latest-delivered revision tombstone and final source ACK semantics. The v2
source ACK must contain the exact captured body delivered to the recipient.
No caller-authored receipt, job list, ACK, completion time or coverage is accepted.

The v2 body contains the unchanged local-state fields plus a versioned extension:

* Destination completion receipts: source-local contiguous sequence and identity,
  source owner, job ID, tray ID, destination, `UNLOAD_COMPLETE`, `completed` and
  `completed_at`. Enumerate all source-owned destination completions through
  capture in their native receipt order, including jobs whose trays have left.
  Filter before assigning source-local sequence; unrelated owners must not alter
  identities. Verify the receipt node equals the immutable job destination.
* Completion coverage: exact owned destination-node scope, cutoff equal to
  `captured_at`, complete-for-scope flag, exact ordered completed job IDs and
  `future_events_included=false`. An empty list means no observed completion in
  that scope, never completion of an omitted obligation.
* Own physical actions: every submitted transfer, route and cancellation, with
  immutable ID/kind and last delivered ACK or null. Legacy empty recovery is
  not a current owner-protocol command; a legacy-control-enabled session is
  outside this contract and must not silently gain complete coverage. The
  reference format includes terminal entries for auditability; unbounded runtime
  histories may later need a separately specified authenticated compaction.
* Action coverage: exact submitted and unresolved ID lists, source/cutoff and
  explicit exclusion of unsubmitted Python plans. Terminal resolution is checked
  against operation kind, not a universal set that treats `delivered` as a
  successful route. Unknown kinds and missing ACKs fail closed. A terminal
  rejected operation ends that operation, not its business obligation.

All extension fields and derived coverage belong in a distinct v2 typed digest
and checkpoint section. Retain the v1 typed serializer byte for byte. Derive
completion rows from existing receipts when capturing, so ordinary/v1-only runs
need no new global ledger and can retain identical old state seals. A v2-only
checkpoint section should be omitted when no v2 snapshot exists. Native024
performance changes do not remove these source records; no physical model
change is required. Exact implementation still needs root coordination.

## Owner adapter and later rolling execution

Each owner must retain the four immutable job contracts from its own actually
delivered initial self-copy and peer message. Completed-prefix contracts cannot
be loaded from the complete offline experiment input. Match a later completion
receipt against that retained ID/destination contract before setting status.
The pure `planning_capture_v2_contract.py` checks data only and always returns
native-delivery and online flags false. A trusted native adapter must separately
verify loaded module identity, endpoint origin, schema/digest, channel, causal
capture/delivery/self-ACK times and expiry, as the initial adapter already does.

The deciding owner must compare its current submitted physical-action ledger
with the self capture and process all delivered ACKs. Any newly admitted own
action since capture invalidates the self-copy for this restricted model.
The native snapshot cannot see an unsubmitted Python plan or promise that a
peer will remain idle after capture. A common controller protocol must explicitly
quiesce new physical admissions while collecting a pair and reject unsupported
intervening activity. This is a conditional cooperative policy assumption, not
an atomic distributed commit or a native resource reservation. Missing or lost
self ACK may still create asymmetric readiness; retain and test that case.

The first native rolling experiment should use the supported first-return and
loaded-reuse windows, preserve the actual initial policy and all four jobs, and
re-solve from newly delivered v2 facts. At each owner, accept an explicit lineage
root before observation; name the exact new message/ACK trigger and any unresolved
parent operation. Apply only the first currently lawful action. Compare frozen
continuation, strict coordinate, neutral-plateau coordinate and resource-pair
repair with identical information/budget/publication traffic. Keep all gates,
missing/expired/outage cases and model errors; conditional prediction alone does
not certify actual protection or the complete-request100ms target.

There is a concrete lead-time gate to test. Let B observe the actual start of
reuse1's loaded service at7 at time t. B issues a v2 publication; with unchanged
0.01 command delay,0.01 publication delay and0.02 ACK delay, its capture is t+.01,
A receives at t+.02 and B's self ACK arrives t+.04. If A publishes in response to
that delivered message, its capture is t+.03 and B receives at t+.04. B's route
issued then arrives at t+.05, before the0.1 service ends. This calculation assumes
immediate handling of actual native notifications; the existing0.05 policy tick
can consume up to0.05 of that margin. Native same-time ordering, observation
latency, current owner/generation and route commitment must be tested, not rounded
away. No event-loop pause or reduced wire delay is proposed. A's own self ACK is
later, so this schedule does not imply simultaneous readiness or atomic agreement.

At first return, collecting new captures can hold the available empty L at6.
That is a real R2 policy delay, not free information: matched method baselines
need the same publication and collection schedule, and the prior continuation
must also be reported separately to expose any added waiting cost.

## Required native acceptance tests

1. Existing v1-only suites and known native seals remain equal; no caller payload
   can insert completion/coverage; altered v2 fields change the typed digest.
2. A local completion appears only after real destination `UNLOAD_COMPLETE`,
   survives tray departure/reuse, and is absent for other destination owners,
   future arrivals, unload-start, Storage release and failed/incomplete legs.
3. Source-local IDs remain unchanged by unrelated owner completions; capture
   after two completions retains both in order and matches its coverage exactly.
4. Source ACK and receiver get identical immutable bodies; pending ACKs never
   acquire later fields; mutation of returned Python dictionaries is harmless.
5. Lost ACK, pending/granted transfer, future-delivered ACK and unresolved cancel
   remain unresolved. No hidden execution state can clear them. Ordinary
   publication commands are explicitly excluded from physical-action scope.
6. Late/out-of-order delivery, expiry tombstones, owner/recipient outage,
   retry/dedup, checkpoint/fork/restore and consumed-state replay preserve v2
   capture identity and pending coverage.
7. Trusted adapter rejects foreign/stale/tampered receipts, missing retained
   contracts, post-capture local admissions and incomplete lineage. No absent
   job becomes completed; neither owner reads the other's fresh view.

## Native025 acceptance

`native025_build_001/receipt.json` pins the compiled source archive and binary
SHA256 `b024724e3bf0a8e4232eaeb13d99ab6a42018e85e4166acf9081991510ca311b`.
`native025_tests_002.xml` has 69 passing checks: 23 existing v1 tests, 19 native v2
tests and 27 pure extension/adapter guards. The first 68-pass/one-failure run is
retained; its failure was a test-only graph with non-dense node IDs, corrected
without changing C++ or the binary. Sixteen existing native timing runtime
regressions also pass in `native025_existing_timing_tests_001.xml`.

`native025_compat_005/receipt.json` passes all seven checks across twenty serial
branches: protocol disabled, enabled without planning, v1 delivered, v1 lost ACK,
and v1 expired captures. Ordered public outputs, physical results, checkpoint
seals and actual native hidden-state seals match native024, and recording on/off
matches within each binary. The earlier four compatibility attempts retain
driver setup errors around disabled-protocol queries and recorder restart rules;
they are not suppressed or counted as passing branches.

The built `circulation_runtime` CTest passes. A broad CTest invocation also tried
sixteen executables and the unrelated `czr005_cpp` smoke module that this
build-only target did not build; its failures are preserved in
`native025_ctest_all_attempt_001.log`. There is no all-CTest claim. The concise
scope and source-unchanged check are in `native025_acceptance_001.json`.

New timing identity10 (`planning_snapshot_v2`) is intentionally unsupported by
the accepted native022 validator. A separate versioned025 phase-attribution
gate remains required; successful typed message acceptance does not certify
timing attribution or the complete-request100ms target.
