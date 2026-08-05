# G4IRSF16 Stage 16K tail/PIBT supervisor contract A/B

## Scope

This is a deterministic supervisor state-machine contract regression. It is **not** a full closed-loop run and does not measure TTH, mean, p99, maximum, throughput, or causal improvement. The A/B matrix tests which contract capability receives credit; it is not a performance ablation.

T1's local rule is represented only as a local authorization veto that preserves frozen F2. No unrepresented rule movement source is invented. SAFE_HOLD remains a hard supervisor invariant in every row; T0/T1 occurrences are deliberately not credited to those tiers.

## Contract matrix

| Tier | Feature stack | Cases | Tier-credited | Safe holds | PIBT batches | Unsafe | Pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T0 | learned only | 8 | 3 | 5 | 0 | 0 | True |
| T1 | learned + local rule fallback (authorization veto -> F2) | 8 | 3 | 5 | 0 | 0 | True |
| T2 | learned + local rule fallback (authorization veto -> F2) + safe hold | 8 | 8 | 5 | 0 | 0 | True |
| T3 | learned + local rule fallback (authorization veto -> F2) + strict PIBT + safe hold | 8 | 8 | 4 | 1 | 0 | True |

## Evidence

- High-confidence I3 and I4 proposals traverse the learned supervisor states; the local rule veto preserves exact frozen F2.
- Strict PIBT is credited only for T3 and only when the local-blocker, movability, safe-alternative, and atomic-batch gates all pass.
- Model abstention cannot directly trigger PIBT. Invalid batches and forbidden full-A* requests fail closed to SAFE_HOLD.
- Unsafe entries: 0; full-A* uses: 0; all prepared PIBT batches commit all-or-none.

## Interpretation boundary

No tail-performance conclusion can be drawn until the same tiers are run in the original-scale closed loop with preregistered TTH and tail metrics. This artifact only proves the supervisor contract exercised here is fail-closed and attribution-safe.
