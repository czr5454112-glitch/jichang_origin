# G4IRSF22 history lessons and implementation rules

This memo is the short decision table used before changing G22. It records the
business and mechanism evidence that constrains implementation; it is not a new
validation or provenance layer.

| Evidence | Verified result | G22 decision |
| --- | --- | --- |
| G11 event runtime | Local one-step safety held, but only 3,114/28,506 bags and 12,125/43,603 segments completed while peak junction utilization was about 16%. | Keep the event architecture, but never equate locality with capacity. Do not remove central coordination without a concrete local service seam. |
| G11 controller ablations | Current backpressure reduced throughput; retry-only deadlock escape did not improve completed bags. PIBT-lite helped but was only same-bag alternative scanning. | Do not revive generic backpressure or make PIBT the normal congestion scheduler. Preserve bounded PIBT only as a rare recovery fallback. |
| G12/G13 repaired runtime | F2 completed 28,506/28,506 bags and 43,603/43,603 segments with zero conflict, unsafe entry, runtime A*/CIE, future route, or global scan; it was only 1.1347 s/bag behind v2-safe at 1x. | Extend the existing runtime instead of building a second framework. Every G22 action remains one-hop and reservation depth one. |
| G15 exact causal panel | 2,172/2,172 action-changing pairs completed. I3 reroute cost about +42.487 s directly; I4 one-opportunity hold cost about +0.354 s. 56.25% of H_system pairs affected neighbours. | Treat reroute as rare and high-risk. Keep H_bag utility separate from sparse raw-bag/system veto evidence. |
| G16/G17 | H5 improved network time by 0.0585 s/bag but increased source wait by 0.1496 s/bag, ending 0.0910 s/bag worse. Source ordering was not authorized; eager token reservation removed the real decision seam. | Find the correct decision time before training. Do not reopen top-K source ordering or eager future-slot claims. |
| G18 JIT merge | J2 created real bounded-pending service choices and strongly improved 2x. Learned J7 owned 3,500 decisions but changed only 154 and improved mean by only 0.004653 s while adding events. | Freeze J2. Nominal ownership is not progress; do not spend another round increasing merge model ownership. |
| G19 S4 route | Only 90/27,418 matched actions changed, yet 2x mean fell from 851.864 s to 337.843 s and source wait from 502.462 s to 54.666 s. | Preserve S4 exactly as the fallback. Search for a small number of earlier, high-leverage local diversions rather than broad action replacement. |
| G20 E2 and Route pairs | E2 removed about 16-17% of events with identical 1x/2x business results. Of 5,022 exact Route pairs, 102 were beneficial, 4,892 harmful, and 28 neutral; direct/system signs disagreed in 11.35% of sampled H_system rows. | Freeze E2. Do not train a primary-pair classifier; require complete local action sets and sparse system vetoes. |
| G21 complete action sets | In 16 retained 1x groups, every alternate edge and WAIT was harmful; 4 H_system WAIT probes found no external benefit. Lean S4 and scalar beacon yielded only about 1-2% and were removed. | Do not revisit ordinary 1x mutation or micro-optimizations. Audit targeted 2x congestion, then move one real decision earlier if current-point support is absent. |
| 2x remaining gap | S4/J2/E2 mean is 337.842709 s; v2-safe is 247.384666 s; the accepted reported gap is 90.458043 s/bag. | First build a semantic gap ledger and congestion episodes. v2-safe remains offline-only and must never provide runtime future features. |

## Implementation rules

1. The default controller remains `A0 + S4 + J2 + E2` under the existing
   shield, resource semantics, and fault lease recovery.
2. Use only `data/processed/maps/map2.json` and the original distribution-
   preserving 1x/2x/4x task construction. Do not alter the map.
3. Reuse the G20/G21 exact checkpoint engine. Add no second event loop,
   supervisor, full-route planner, global reservation scan, or online oracle.
4. The causal ladder is current point, then nearest strictly earlier
   multi-action decision on the same runtime segment, then conditional
   Merge/Source only if Route support is absent.
5. Future 5/15/30/60-second summaries are branch-local offline measurements.
   They may screen a fixed local-information cost but are never runtime inputs;
   without a held-out objective they are not called a perfect-information
   upper bound.
6. Only an oracle-positive result may unlock guidance. Start with a bounded
   deterministic service-deficit residual; use a monotonic linear residual or
   tiny MLP only if the simpler candidate is demonstrably insufficient.
7. Low confidence means an exact S4 decision. Useful low-coverage mutations
   are preferable to broad ownership.
8. Do not spend the round on new hash/seal/validator families. Record compact
   scientific outputs, tests, and the ideas supported or rejected by results.
