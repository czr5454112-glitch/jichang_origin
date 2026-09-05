# DH finite body clearance V5: pre-result contract, 2026-09-05

This contract was recorded before the V5 full-map2 result. V5 represents the finite time needed for a carrier body to clear an upstream boundary. Clearance is derived from `(map AGV length + map safe length) / incoming edge speed`, rounded up to the existing 0.2-second tick. For map2 this is 1 m / 2.5 m/s = 0.4 seconds. No additional tunable duration is introduced.

At through completion the node's exclusive service identity is released at the same time as in the control. The bag starts its original 2-second total transfer timer and retains the upstream footprint only for the derived clearance interval. At clearance completion the footprint is removed and the bag spends the remaining interval in the existing off-edge transfer state. **The transfer ready timestamp stays through-completion + 2 seconds; clearing the body does not restart the timer.** Subsequent outlet HOLD remains the parent's off-edge behavior. Source induction, goal handling, FIFO, route policy and coefficients are unchanged.

This is a coarse geometric hypothesis: it treats initial boundary clearance as aligned with incoming belt speed and approximates the moving body by retaining its existing discrete upstream footprint during that interval. The map establishes length and speed, but does not establish that this is the geometry of the inferred 2-second transfer. The new Demo3D code uses actual geometry and configured components; V5 does not claim to reproduce it. V5 only tests the difference between instantaneous footprint removal and finite body clearance. It does not solve the separate question of unlimited off-edge waiting after the outlet remains blocked.

To keep this a split of the existing transfer, the implementation explicitly requires `0 < clearance ticks < existing transfer ticks`. Unsupported geometry fails rather than clipping or extending either time. Map2 and the declared fixtures satisfy the domain. Longer-clearance geometry would require another explicit contract, not silent extrapolation.

The method is `FENG_DH_BOUNDARY_CLEARANCE_V5`, with five CRLF sources at `benchmarks/java/feng_cie_dh_boundary_clearance_v5/App`. Source aggregate SHA-256: `7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7`; 33-class aggregate: `0859243f372689bc6167b328f65b743e145eb323e375f0aaee56be4aeb60079e`. The parent files remain untouched. Policy and lattice sources are byte-identical to the parent; simulator/bag-state implement the lifecycle and Benchmark uses distinct method labels.

| Mechanism fixture | Verified result |
|---|---|
| Single bag, zero/positive intermediate through | Completion ticks 28/33 and first admission tick 10, unchanged from control. |
| Positive through seeded at boundary | Through starts 1, transfer starts 6, upstream clears 8, outgoing admission 16. Original transfer-ready tick 16 is preserved through clearance. |
| Zero through seeded at boundary | One zero service and one transfer start; clears tick 3, outgoing admission tick 11. A duplicate clearance start is rejected. |
| Map dimension sensitivity | Changing body length from 1 m to 1.5 m changes clearance from 2 to 3 ticks; total transfer ready stays 16. No hard-coded 0.4-second dwell. |
| Two followers on one incoming edge | Through starts ticks 1,10, compared with control 1,8: +0.4 seconds on that contention interval. |
| Two incoming ports | Through starts ticks 1,6, unchanged: body clearance does not become node-wide exclusivity. |
| Long finite through service | Completes at tick 128 even with deadlockIdleTicks=2; finite timers count progress. |
| Blocked outlet | Upstream clears tick 3 although outlet stays blocked; the bag waits off-edge with unchanged ready tick 11. This deliberately verifies the limited scope of V5. |

All 9 fixtures passed twice; the complete 12 generated evidence files (9 traces, results, empty stderr and manifest) were byte-identical on repeat. Each step checks lattice integrity and unique bag/edge ownership, and a bag in clearance must retain a stopped physical footprint. Fixtures require eventual completion and one-shot timers.

Reproduction, with no full experiment launched:

```powershell
python scripts/eval/derive_feng_dh_boundary_clearance_probe.py --verify
```

Evidence: `outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_fixtures/derivation_and_fixtures.json`; build `build/feng_dh_boundary_clearance_v5`; test source `tests/java/App/BoundaryClearanceAudit.java`. The generator derives from the frozen control, checks exact transformation anchors, refuses differing existing probe sources, and records physical-byte identities and commands.

Full-map2 interpretation follows the current [shared-input protocol](feng_dh_map2_reaudit_protocol_20260905.md), preserving all 28,506 bags and 43,603 legs and comparable sum-of-leg THT. Report direction, distribution and mechanism evidence regardless of closeness to historical output. A pre-declared joint variant that also checks an already-stopped outlet before boundary departure would be a separate hypothesis; it must not overwrite V5 or be chosen after observing which numerical output is most convenient.
