# Delivered-protocol query reuse: source proof and prototype

This is a separate, unintegrated optimization experiment. It does not change
the accepted LT2 timing requirement, remove pending requests, or close an update
on an estimate. The [prototype](../../scripts/experiments/g31_ics_circulation/protocol_query_cache.py)
uses only local submitted payloads, returned owner notifications and earlier
public query results. No native cache experiment has run.

## Source contract

`render_protocol_request` returns request identity, local client status/attempt,
the last actually delivered immutable ACK, and a fixed resolution label.
`render_protocol_command` similarly returns identity/kind, status/attempt and
the last delivered ACK. Demand capture content and planning-snapshot content in
a final command ACK are immutable; planning status is rendered at the ACK's
completion time, not today's time. Physical transfer progress alone does not
change these projections before an ACK is delivered.

In the inspected native implementation, the three changing paths are:

| Changing path | Required invalidation |
| --- | --- |
| This client submits/retries the exact operation | Invalidate its owner/operation cache entry before every submit, including rejection or exception. |
| A protocol ACK is delivered | Owner notification bit 16 invalidates all cached queries for that owner. Dropped ACK handling supplies no delivered knowledge. |
| Local transport timeout changes `client_status` | Owner notification bit 32 invalidates all cached queries for that owner. It does not establish physical failure. |

This proof applies only under exclusive serial access through the wrapper. The
native notification mask resets at each new timestamp; a latest mask is not a
cumulative change log. The wrapper therefore accepts reuse only after a complete
`advance_until_owner_notification` boundary with all declared cached owners
subscribed and the exact cursor from its preceding boundary. A cursor gap,
partial timestamp, missing subscription, invalid notice, unknown notification
bit, exception, direct advance, unknown method, checkpoint, restore or fork
clears cached values and the continuity proof. A new complete boundary can
establish a fresh empty baseline. Fork children start empty. No proof or cached
value enters physical or controller checkpoint state.

The native advance stops at the first complete subscribed notification boundary.
Consequently, consecutive certified calls cannot skip an earlier ACK timestamp
and trust an unrelated later mask. Multiple changes at the same timestamp are
ORed; a second same-time cascade with a new sequence is checked again. The
wrapper returns independent dictionary copies and preserves explicit policy and
recent-forecast endpoint capability.

The [20 pure tests](../../outputs/experiments/g31_ics_lt2_sustained_20261014/protocol_query_cache_tests_002.xml)
cover alias isolation, ACK/timeout invalidation, lost-ACK pending behavior,
unchanged immutable retries, rejection cooldown, same-time cascades, lost-mask
counterexamples, cursor/subscription gaps, restore/fork, and actual
`ProtocolClient` state/call equivalence on a fake protocol session. These are
source-contract tests; they do not replace real native equivalence or speed
measurements.

## Recorded opportunity and limits

A read-only census of all ten raw segments in
[bundle002](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_bundles_full1x_5000_002/manifest.json)
found 16,115 refresh queries across 5,000 owner activations and 1,186 protocol
identities. Of these queries, 13,539 returned exactly the previous view for that
identity; 9,573 were identical and had neither ACK nor timeout in that activation's
current notification mask. The longest pending identity was queried 1,628 times.
These are retrospective equality counts, not an online certificate that those
queries could all be omitted.

The actual [native022 short-prefix phase evidence](../../outputs/experiments/g31_ics_lt2_sustained_20261014/native022_acceptance_001/native022_on/original1x_prefix_phase_report.json)
has 185 command queries consuming 1.2697 ms of measured outer query envelopes,
versus 355.9683 ms for 569 recent-policy observations. That early prefix contains
no transfer submissions. It does not establish the later pending-transfer cost
or identify polling as the dominant algorithmic bottleneck.

The generic wrapper must deepcopy a cached public dictionary, which could cost
as much as native serialization. Integrating the proof inside `refresh` could
also avoid replacing an unchanged `row.client_view` while retaining the returned
diagnostic copy. That integration is deliberately deferred until the 5,000-update
native phase evidence identifies useful cost. Retry deadlines, ACK processing,
rejection cooldown, operation identities and all pending/open denominators must
remain unchanged. Independent new decisions can refer to an older reservation
without extending its obligation; the actual query/retry/ACK continuation of
the older immutable operation remains charged to it.
