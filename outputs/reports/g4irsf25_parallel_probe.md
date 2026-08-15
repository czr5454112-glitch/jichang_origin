# G4IRSF25 S4 parallel probe

## Decision

- **Same-stream node-parallel: NO_GO_ON_TESTED_512_WINDOWS**
- **Two independent S4 runs in ThreadPool: GO_BATCH_THROUGHPUT_ONLY**
- Deployment scope: **offline_or_independent_runtime_batch_only**
- The measured speedup is **offline/batch aggregate throughput across independent complete simulations, not a default for one live order stream**.

## Exact evidence contract

- Controller: `A0+S4+J2+E2`
- Throughput lifecycle segments: 43,603
- Release trace: `artifacts/datasets/g4irsf24_release_compact.csv`
- Release binary: `build/g4irsf24_dlp_release/python/czr005_cpp.cp311-win_amd64.pyd`
- Release binary size: 2,431,488 bytes
- Canonical prefix: 512 segments; release span 18787.000s (8267.000 to 27054.000, 0.027/s); retained 39,721 / 41,321 processed event rows (96.1%) and 3,504 complete decision/hold rows.
- Densest release window: 512 segments; release span 340.000s (22633.000 to 22973.000, 1.506/s); retained 44,453 / 46,420 processed event rows (95.8%) and 3,949 complete decision/hold rows.

The second canary is selected deterministically from the full exact-release
lifecycle: sort by `(release_epoch, segment_id, canonical ordinal)`, scan every
contiguous 512-row window, minimize release span, and resolve ties by segment
ID/ordinal.

## Same-stream opportunity

Events were grouped by `(time, reconstructed E4 microphase)`.  A work item may
share a wave only when its conservative node footprint is disjoint.  The
footprint includes current node, edge endpoints, and linked candidate
downstream nodes; unknown and fault/repair work is a global barrier.

| Window | Event coverage | Event observed width / fraction | Event optimistic upper width / fraction | Decision width / fraction | Window result |
|---|---:|---:|---:|---:|---|
| Canonical prefix | 96.1% | 1.094 / 0.166 | 1.138 / 0.198 | 1.087 / 0.157 | NO_GO_ON_PREFIX_512_CANARY |
| Densest release window | 95.8% | 1.645 / 0.634 | 1.718 / 0.650 | 1.610 / 0.623 | NO_GO_ON_PEAK_RELEASE_512_CANARY |

- Canonical prefix: optimistic event bounds include all 1,600 untraced processed rows as perfectly parallel work.
- Densest release window: optimistic event bounds include all 1,967 untraced processed rows as perfectly parallel work.

The prefix result is scoped as `NO_GO_ON_PREFIX_512_CANARY` when it misses the
gates; it is not a universal same-stream result.  Combining the prefix with
the deterministic peak-density window yields **NO_GO_ON_TESTED_512_WINDOWS**.
Both tested windows definitively miss at least one required width/fraction gate, including the optimistic event upper bounds.

This is a feasibility audit. The active S4 runtime still executes one serial event loop,
and the current recommendation remains **defer implementation**.
These two 512-segment windows cannot be extrapolated to a larger map or a new
workload. A same-stream implementation would need immutable phase
snapshots, node-footprint staging, validation, and deterministic commit in the
original `(time, microphase, seq)` order. Assigning one mutable policy object
to each node without that commit barrier is unsafe because corridors, J2, and
PIBT cross node boundaries.

## Independent-run throughput

| Mode | Aggregate events/s | Aggregate wall (s) | Median pair wall (s) | Median individual wall (s) | Median overlap |
|---|---:|---:|---:|---:|---:|
| Sequential | 229307.7 | 69.705 | 34.852 | 17.547 | 1.000 |
| ThreadPool(2) | 390055.5 | 40.978 | 20.489 | 19.694 | 1.922 |

- Aggregate speedup: **1.701x**
- Batch throughput gate: `>= 1.70x`
- Gate clearance: **0.001x**; treat this as a machine-local batch result, not a robust production margin.
- Parallel individual-wall regression: **12.2%**
- Individual-wall latency guard: `<= 10%` -> **False**
- Every run business/safety equivalent: **True**
- Sequential lane order: `alternating`
- Pair mode order: `alternating`

## Recommended scheduling boundary

This result supports only offline batch work across mutually independent runtime jobs or simulator instances. It does not implement order-stream routing and does not authorize parallel execution as the default for one latency-sensitive live stream.

Keep a single live order stream serial until the phase-snapshot/staged-commit
design is implemented and revalidated against exact in-memory business and
safety projections.
