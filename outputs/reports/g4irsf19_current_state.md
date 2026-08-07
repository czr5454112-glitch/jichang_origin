# G4IRSF19 current state

## Decision

G19 selects the smallest verified decentralized controller:

```text
Source: A0 existing release behavior; no learned Source promotion
Route: S4 local queue/calendar-aware one-hop rule
Merge: J2 destination-owned bounded-pending JIT grant
Boundary: E4/R3/P2/Q0/C0 safety and resource checks unchanged
```

This is a research mainline, not a production or learned-controller promotion.
It moves routing from centralized future-route planning toward local MAPF-style
decisions without adding another orchestration layer.

## Main evidence

| Result | Evidence |
|---|---|
| 1x complete | mean/p95/p99 TTH 213.912/252.004/281.004 s; every hard gate passed |
| 2x complete | mean/p95/p99 337.843/960.004/2,242.954 s; source wait 54.666 s |
| 2x improvement vs J2/S1 | mean -514.021 s; p95 -3,709.421 s; p99 -5,143.234 s; source wait -447.795 s |
| Route action evidence | 90 directly matched S4 mutations among 27,418 matched branch opportunities at the 8,192 prefix |
| 4x bounded frontier | 27,872/174,412 complete in 60.828 s; backlog 14,694; bounded native return |
| 4x gain vs S1 | 53.05% more completed bags at the same wall boundary |
| rollout parallelism | two repeats: P2 1.863x/1.966x, P4 3.289x/3.330x, P8 5.247x/5.325x |
| fault safety | both 8,192 fault cases complete; zero physical fault-edge entry violations; all affected bags complete |

## Negative results retained as decisions

- Source ordering produced 0 alternative proposals and 0 mutations after
  62/238/8,335 evaluations at 144/512/8,192 segments.
- Source pressure A1/A2 both worsened 2x mean TTH and source wait versus A0;
  neither is promoted.
- Learned Route S2 owned 57,539 of 59,826 observable decisions after its risk
  gate, but changed 0 matched actions and changed 0 business metrics. Ownership
  without action or benefit is not treated as success.
- S3 also produced 0 matched mutations. No new residual, MLP, or set model was
  trained after these action-seam results.
- Native checkpoint BOLT-P P1 has strict replay parity, but P2/4/8 was not run
  because the measured per-worker memory envelope makes P8 unsafe on this
  machine. Process rollout speedup is not relabeled as shared-runtime commit.

## Engineering delivered

- O(1) native progress snapshots and a wall-bounded return that does not
  finalize partial state;
- an append-only Python/native bounded-call ABI while preserving the historical
  unbounded call shape;
- E4/J2 access to existing S1/S2/S3/S4 scorers without relaxing R3/P2/Q0/C0;
- deterministic process-isolated rollout, executable BOLT-P P1, Route, Source,
  capacity, and fault campaigns with compact atomic outputs;
- complete raw decision/wait traces are discarded after compact aggregation.

## Verification and boundary

The final local gate uses the fresh G19 native extension: 123 focused Python
tests passed, three native C++ regression executables passed, all new Python
drivers compiled, and `git diff --check` passed. G18 GitHub Actions Run #61 was
already green. G19 remote CI is evaluated only after this commit is pushed.

The evidence proves a measurable decentralized local-control improvement and
process-level experimental parallelism. It does not prove a learned multi-head
controller, resumable serialized native state, multi-machine message ordering,
or parallel commit inside one mutable event runtime.
