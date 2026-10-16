# Native022: 5,000-update accounting and diagnostic retention

The [capture](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_native_timing_full1x_5000_001/manifest.json)
finished with unchanged sources and passed its serial uninstrumented replay.
It uses the accepted immutable native022 archive and the frozen current Python
controller, not subsequently edited C++ sources. The
[process receipt](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_native_timing_full1x_5000_001/process.json)
retains 175.769 seconds for measurement, evidence generation, analysis and replay;
measured controller windows total 26.767 seconds. This is instrumented,
non-isolated research evidence, not a production speed comparison.

The offered population is unchanged at 28,506. The declared horizon is 86,400;
the fixed 5,000-activation prefix stopped at 12,249.637986 with 57 arrivals
observed. All ten raw 500-activation segments were saved. The prefix does not
complete the declared physical horizon or the ten still-open protocol roots.

## What the independent checks establish

[Raw execution verification](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_native_timing_full1x_5000_001/independent_raw_verification.json)
matched all 5,000 owner roots, 9,306 native advances, 1,186 protocol identities and
1,368 submission attempts against the saved bundle ledger. It checks payload
hashes, root identities/causes, ordering, lifecycle, full outbox retention and
inner/outer interval containment. The serial replay matched all eight recorded
semantic categories, including calls, decisions, native boundaries, controller
state and final native seal.

The native phase trace contains 57,544 spans and 37,935 outer calls. An independent
reread recomputed exactly the saved phase partition. The full native envelope is
9.9737681 seconds: identified control bundles 9.5853055 seconds, unclassified
native remainder 0.2093506 seconds, and Python binding remainder 0.179112 seconds.
Every part remains charged. No physics subtraction or refined per-business-root
total is claimed.

There are 3,818 no-action roots, 1,172 completed roots with messages and ten open
roots. Among the 4,990 closed roots, 2,785 conservative complete bounds are at
most 100 ms and 2,205 exceed it; all ten open roots also have known prefix bounds
above 100 ms. The largest closed bound is 4,732.5884 ms, comprising full owner
bundles 3,642.4647 ms, scheduler gaps 613.7076 ms, native advances 345.7502 ms and
returned output 130.6659 ms. These are conservative owner-update totals, not
isolated business-request latencies. An upper bound above 100 ms does not prove
the corresponding isolated request exceeded 100 ms.

## Measured work, not inferred bottlenecks

[Method diagnostics](../../outputs/experiments/g31_ics_lt2_sustained_20261014/request_native_timing_full1x_5000_001/independent_phase_diagnostics.json)
retain these actual outer envelopes:

| Native method | Calls | Total ms |
| --- | ---: | ---: |
| Recent policy observation | 6,146 | 8,820.3306 |
| Demand signature | 5,000 | 537.9979 |
| Notification advance, including all physics | 9,306 | 391.2982 |
| Transfer query | 11,889 | 111.6223 |
| Command query | 4,226 | 37.4202 |
| Command submission | 1,173 | 69.0273 |
| Transfer submission | 195 | 6.0716 |

The most repeatedly queried protocol identity used 22.6334 ms across 1,628 native
queries. Query costs are real continuation work, but this evidence does not make
query serialization the leading optimization target. Python refresh copies and
policy work are outside those individual native envelopes.

Two owner activations exceed 100 ms: 125.4233 and 123.0053 ms in the outer wrapper,
with inner policy wall times 124.8764 and 122.1649 ms; both inner CPU readings are
125 ms. Their nested native calls account for only 2.6557 and 2.8394 ms. The first
issues no new request, service action or publication; the second issues one
service action. Therefore native validation cannot explain these two spikes.
GC over retained diagnostic objects is a plausible source, but this run has no
GC callback evidence and cannot establish that attribution.

## Proposed lossless diagnostic streaming experiment

This proposal changes diagnostic retention, not policy, clocks, offered workload,
request completion or accounting requirements. GC stays enabled. Every pause
inside a required service interval stays in the measured interval.

First stream only the native timing sidecar. `NativeTimingCapture` currently
retains every envelope and batch, including repeated cumulative identity tables.
Introduce a monotonic call ordinal independent of list length. After each complete
returned controller call, export the new envelopes and native `take()` batch to
an immutable numbered shard with a hash, emitted-span range, call range and
session/epoch identity. Drop only in-memory diagnostic references after the file
is saved. Retain counters, sticky errors and namespace identity. Do not reset the
native epoch, omit cumulative identity tables, or subtract export/GC time from
any measured controller interval. Reassemble and run the existing validator only
after measurement. Record export and reconstruction process costs separately.

The coarse recorder needs a separate second step. It cannot simply discard old
bundles: `_link_trigger` can attach a later pending-owner root to a prior native
boundary, its initialization/gap and returned-output cohort. Use an append-only
journal of immutable rows plus explicit association/status patch records. Retain
the current service window, active roots/messages, unconsumed notification/timer
origins and compact immutable operation-ID/payload-hash metadata. A later
association to an already written bundle becomes a patch record, not a mutation
or omission. Offline reconstruction must reproduce the original ledger structure,
including no-action drains, open roots, prior-window trigger links, all shared
cohorts and original order. Never prune controller/native request histories.

Add a bounded diagnostic GC event buffer. Record start/end monotonic times and
current owner/root/native nesting; flush outside controller calls. Compute
interval overlaps offline rather than assigning a pause only to the owner at
its start. Buffer overflow invalidates the GC attribution instead of silently
dropping events. Do not call `gc.collect`, disable GC, write files inside the
callback, or use its readings as policy inputs.

The paired experiment must predeclare the same complete input, initial native
state, current Python sources, controller/physical budgets and native binary for
retained and streamed arms. Require exact submitted payloads/retries, decisions,
public outputs, native boundaries/state seals and reconstructed ledger structure
after excluding timestamps; all raw evidence and no-action/open denominators
remain. Include serial uninstrumented control and per-interval GC overlap.
Changing diagnostic retention can reduce observer overhead, but cannot by itself
prove the underlying controller algorithm meets the business-request 100 ms
requirement. No new streaming implementation or native experiment is asserted
by this document.
