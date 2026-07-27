# G4IRSF13-D Interaction Isolation

Status: `PARTIAL_WITH_EXPLICIT_BLOCKER`.

The matrix is executed only on the protected real map and unchanged real task rows. Blank metrics mean `NOT_RUN`; they are not zero.

## Current evidence

- Executed/cached rows: `49`.
- Explicitly rejected rows: `5`.
- Measured priority selection: `Q0`.
- Execution status counts: `{"EXECUTED": 49, "NOT_RUN": 41}`.
- C7 publishes only a real merge slot; C8 activates only on local contention evidence and must degrade to C0 under low load.
- C5 and C6 have the same pressure/credit vector when both use P2. Their duplicate configuration is retained and not misreported as an independent causal contrast.

## Early rejection

A candidate is rejected before 8192 for incomplete drainage, any hard safety/architecture violation, >1 s/bag matched mean loss, >2 s p95 loss, >4 s p99 loss, a source-wait gain more than offset by network loss, or a material PIBT rollback surge.

## Claim boundary

Motif, 144, 512, 2048, and 8192 are successive-halving diagnostics. Only up to four explicitly authorized finalists may run full. B2 is a legacy-order one-step diagnostic and can never be a finalist. No runtime A*, future route, or global reservation scan is admitted.
