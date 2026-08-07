# G4IRSF18 BOLT-P trace parallelism census

Status: **`TRACE_BUCKET_CENSUS_COMPLETE_NOT_EXECUTABLE_FRONTIER`**.

This is the zero-thread M0 census proposed by the BOLT-P method. It
groups merge opportunity rows by exact IEEE-754 timestamp and builds a
stable local-scoring pack using role-unified junction, request and
directed-edge keys. It is a screening estimate of micro-batch potential,
not an executable event frontier or multi-core execution result.

| Scope | Opportunities | Exact-bit time buckets | Max bucket | P95 bucket | Max local-scoring pack | P95 pack | Opportunity share in multi-score buckets |
|---|---:|---:|---:|---:|---:|---:|---:|
| All merge | 27,153 | 25,439 | 2 | 2 | 2 | 1 | 0.022% |
| Multi-candidate only | 935 | 920 | 2 | 1 | 1 | 1 | 0.000% |

Trace completeness: **`PASS_COMPLETE_ZERO_DROPPED`** (`28,352` stored, `0` dropped).

## Interpretation

- A pack above one means rows in that timestamp bucket have disjoint
  declared local-scoring keys. It does not prove they were simultaneously
  live in the event heap or that their commits commute.
- The narrow p95 offers little merge-only exact-bit batching opportunity
  in this trace; route/source instrumentation, event-loop cost and
  process-isolated rollout throughput should be measured next.
- J7 coverage, kill-switch state, generation validation, telemetry and
  event publication are intentionally excluded from the scoring keys and
  must remain in the canonical serial coordinator.

## Claim boundary

- Trace contains merge opportunities only; route and source are not measured.
- Timestamp buckets are not executable event frontiers: event sequence, frontier epoch, parent causality and dynamic PIBT footprints are absent.
- Resource keys cover local scoring only; global policy state and commit lanes remain canonically serial.
- Greedy local-scoring width is not a maximum independent set or a commit width.
- Exact-bit grouping is stricter than the runtime's epsilon-based same-timestamp relation.
- Exact-bit timestamp co-occurrence does not establish wall-time speedup or physical capacity.
