# Draft: source-observed in-flight facts for planning capture v3

This is an information-contract proposal for a separately accepted future
native version. It does not change v1/v2, existing permissions, route actions,
FIFO, tray stock, capacities, travel times, wire delays or saved results. No v3
message has been delivered in the recorded studies. A pure validator accepts
supplied data conditionally; only a separately verified native read adapter
could authenticate an actual delivered message. Neither fact validation nor
delivery establishes model protection or atomic agreement between owners.

## Exact version boundary

The proposed capture schema is `g31.planning_capture.v3`. `capture_v2` embeds
the exact existing v2 capture, including its v1 body, destination-owned terminal
receipts and own submitted-action coverage. Existing API/digest/checkpoint
behavior remains unchanged when no v3 operation exists. The new operation,
recipient endpoint, vector and digest need their own acceptance. Timing
identity 11 is a proposal requiring an explicitly versioned validator; it
must not be silently accepted by the existing 022 or 025 timing contracts.

The proposed typed digest starts with the existing fingerprint namespace
string, the `g31.planning_capture_digest.v3` domain and the v3 schema. It then
encodes `nested_unchanged_v2_typed_digest` and the **computed v2 typed digest
string** of `capture_v2`, followed by the typed extension fields. It does not
inline v2 bytes or accept a caller-supplied nested digest. Both the embedded
v2 body and its existing digest algorithm remain unchanged. Validation-result
flags below are not wire fields and do not alter these digest bytes.
The proposed v3 typed digest is domain-separated and nests the computed
unchanged v2 digest **string**, then the typed v3 extension. It does not inline
v2 bytes or trust a caller-provided v2 digest. The v2 body itself remains the
exact nested public data and retains its existing independent checks.

The extension uses this field vocabulary, shared with the new pure contract:

```text
extension.schema = g31.planning_inflight_receipts.v1
extension.source_owner
extension.captured_at
extension.source_observed_inflight = [
  {source_owner, receipt_event: EDGE_ENTER,
   tray_id, business_bag_id, generation, traversal_id,
   edge_from, edge_to, entered_at,
   static_edge_travel_seconds, derived_edge_exit_at}
]
extension.coverage = {
  scope: all_current_source_owned_committed_edges_with_matching_observed_entries,
  source_owned_inflight_tray_ids,
  capture_cutoff,
  complete_for_declared_source_inflight,
  unmatched_tray_ids,
  uses_future_event_heap: false
}
```

`traversal_id` is the existing **public per-tray traversal version**. Native
matching may use a private active-leg/global traversal key internally, but
neither key is exported. `generation` is the captured current tray generation.
It must match the actual source-local tray and receipt association; it is not
an arbitrary caller parameter. The five-obligation fixture still requires
every job contract and both completed-prefix receipts already required by v2.

## Capture and causal authority

The publisher must own the moving tray's retained source node at capture time.
The captured tray must still identify the same job, generation, public
traversal version and committed edge. Native capture requires both its
`edge_entry_observed` marker and a matching already observed EDGE_ENTER
receipt, tied internally to the current active leg, private traversal, tray,
job and endpoints. The receipt time must be no later than capture. A reused
tray's earlier entry, a different carried job, a remote owner receipt, or an
empty-transfer ACK from an earlier stage cannot substitute for that match.

The source derives travel from the unchanged public static edge record and
derives exit as the same native arithmetic `entered_at + travel`. It must not
read the future event heap or report a queued EDGE_ENTER as an observation.
Edge commitment can precede actual entry. Such a tray belongs in the declared
committed-edge denominator and `unmatched_tray_ids`; it has no observed-entry
row and keeps the dependent prediction unknown. The coverage Boolean cannot
erase an unmatched tray. Empty lists are valid only for an explicitly empty
current source-owned committed-edge population.

The immutable body is captured when the command actually executes. The peer
can use it only after actual planning-message delivery and before its expiry;
the source can use a self-copy only after its delivered final ACK. Retries
reuse the identical request and immutable captured body. A fabricated body,
caller-supplied delivery time, missing self-ACK, dropped peer message or
undelivered source publication never upgrades a verification token. Two
owners can have different readiness; this extension does not add a commit
barrier or infer peer readiness from the other owner's self-copy.

## Receiving occupancy and time domain

Native receiving capacity is already reserved by the committed `edge_to`.
This is an identified physical occupancy contribution, not a newly granted
resource or a separate empty-transfer lease. For supplied captures with equal
physical timestamps, check source trays and target-owned node occupancy using the native
OR rule: a tray contributes at most once to a node if it is stationary there,
committed into it, or has a matching reception-node reservation. Deduplicate
only the same tray/generation/public-traversal identity. Conflicting states
for that identity, duplicate IDs with different identity fields, extra
occupancy or a missing owner population fail closed. Reconcile target
`unrepresented_occupancy` with the exact incoming identities; subtracting an
unidentified count is insufficient. The result is only consistency of the
supplied populations and counts. It is not proof that those source states
ever coexisted or that remote occupancy remains unchanged at the deciding instant.

Equal `captured_at` values do **not** identify one atomic native cut. Different
source publication commands can run at different event-order positions within
one physical timestamp, with reservations, receipt publication or local state
changes interleaved. Matching per-source publication sequences, common static
digests, identified incoming trays or aggregate occupancy counts do not rule
out those intervening events. Actual native provenance and delivery would
authenticate the individual source captures, but would still not establish
that additional cross-source invariant. No barrier or global event sequence
is inferred or introduced by this extension.

The pure reconciliation status is
`conditional_same_timestamp_occupancy_consistency`. It reports only that the
supplied capture timestamps agree, and keeps `atomic_capture_cut_verified`,
`simultaneous_state_certified`, `intervening_events_excluded`,
`current_state_certified`, native delivery/protection and independent v2
validation flags false. Unknown results also retain those false flags.
A future joint predictor must separately prove invariance over possible
intervening transitions or validate an explicit synchronization contract
before treating the inputs as one simultaneous state. Equal timestamps alone
cannot authorize a joint action or certify per-job protection.

The first supported consistency domain requires equal capture time and full
declared owner/node/tray coverage, while still retaining the atomic-cut
limitation above. Existing age limits remain unchanged.
Equal capture timestamps do not establish one atomic native event-order cut:
two source commands can execute at different positions within that timestamp,
with physical or reservation changes between them. Conservation checks only
consistency of the supplied source captures. They do not prove simultaneous
state, synchronize owners, or justify a hidden global event-sequence field.
A later predictor needs a separately justified invariant over intervening
transitions; `current_state_certified` must remain false here.
Require `entered_at <= captured_at <= delivered_at <= now < valid_until` and
`now < derived_edge_exit_at` before projecting the same in-flight state. An
arrived or equality-at-exit message is stale for this representation even if
its envelope has not expired. It cannot prove arrival, loading, service start,
unload completion or a new free berth. Those transitions need a newer lawful
capture or a separately proved conservative transition model. Known faults,
unresolved actions, unmodeled future commitments or unmatched coverage retain
unknown status. No negative per-job tolerance is introduced.

## Counterexamples required before native acceptance

Native tests must include: committed reservation before actual EDGE_ENTER;
missing or wrong-entry receipt; private/global traversal confused with public
version; reused tray with old generation/job; a later edge whose source owner
differs; source/target owner mismatch; zero/changed public travel; capture
exactly before/at/after entry or exit; expired latest revision as a tombstone;
duplicate publication/retry without recapture; lost self-ACK with delivered
peer and its opposite asymmetry; outage-deferred capture and delivery; mutated
payload/digest; checkpoint restore before/after capture and delivery; pending
physical action coverage; equal physical timestamps with different capture
event positions, including changes that leave aggregate occupancy unchanged;
two incoming trays whose aggregate count fits but
whose identities do not; and a tray counted both as parked and incoming.

Compatibility gates must compare no-v3 and v1/v2 ordered public output and
hidden state seals with the accepted binary. V3 needs explicit digest,
source-self-copy/peer-body equality, exception/overflow handling and versioned
timing acceptance. All failed, censored and unexecuted rows remain visible.

## What the existing four moving-E cases establish

`inflight_capture_bounds_audit_002.json` independently audits all twelve saved
rolling002 branches and twenty-four later decisions: four contain moving E,
twenty are stationary, and all 67 saved-evidence checks passed. In those four
old gate-0 decisions, B already owns E on 3→4 and its own lawful current view
contains the receipt-derived exit time 7.801. The offline audit matches that
time to the saved actual EDGE_EXIT. The earlier generic `capture + travel`
upper-bound claim in audit001 was withdrawn because commitment may precede
entry; audit002 retains all four public-only bounds as unknown. This does not make A's node-4 occupancy
identity known to B without combining the delivered capture scopes, and does
not upgrade the old stationary model. All four old unknown fallbacks remain.

Hypothetically adding the matching source-observed entry tuple to a real new
message could make that identity/arrival input explicit to a peer. In the new
third-tray long-occupancy fixture E may instead be on 1→3 under A when B must
decide; B cannot borrow A's current local exit field. That is the information
gap the proposed extension addresses. It has not yet been closed by an actual
v3 delivery or validated native prediction, and no protected gain is inferred
from this hypothetical replay.
