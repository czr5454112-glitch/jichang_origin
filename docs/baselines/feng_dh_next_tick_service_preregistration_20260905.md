# DH next-tick service reuse: pre-result contract, 2026-09-05

This note precedes the V4 full-map2 result. V4 tests when a newly eligible bag observes a just-finished node-through service as free. Its parent allows a grant on the same commit that ends the previous service: `occupant == null || nodeThroughDepartures.contains(nodeValue)`. V4 uses only `occupant == null`, so a service still occupied in the decision snapshot can be reused on the next tick. The sole executable semantic edit is that availability expression; METHOD and auxiliary control labels are also distinct. Node-through service remains exactly the map duration, the per-bag overlapping off-edge transfer remains 2 seconds, and zero-through handling, source admission, movement, scoring, coefficients, arbitration order and population are unchanged. This is an observation-timing probe, not an added unconditional per-node dwell.

The English primary description's sequential bag update and the legacy HCA's closed node reservation intervals motivate testing whether ideal same-commit reuse is consequential. Neither establishes this as the original DH implementation. Conversely, same-commit reuse is not proved wrong by its being optimistic. The primary source boundary is in [the independent audit](feng_dh_primary_semantics_reaudit_20260905.md). New Demo3D component evidence does not yet connect this Java timer model to an active original DH component, so V4 receives no source-exact endorsement from it.

Source directory: `benchmarks/java/feng_cie_dh_next_tick_service_v4/App`; METHOD `FENG_DH_NEXT_TICK_SERVICE_V4`. Source aggregate SHA-256: `c59fd6ccae5a8d405e18fd72bf29a2979e1f3d1278e8b5fa526d0b233176e419`. Compiled class aggregate: `853560a300ac24d341368ee3fce9fbcd7808c7bbb3f044955ecce91b68cd8f87`. Sources are CRLF and the aggregate follows the external runner's length-prefixed name/content convention. Only Benchmark labels and the Simulator availability expression differ from the frozen parent; no parent file is changed.

Four tiny cases were run on both parent and V4, with physical ownership and lattice integrity checks after every tick and eventual completion required:

| Mechanism | Parent | V4 |
|---|---|---|
| Two incoming ports, one-second through server | service starts at ticks 1, 6 | ticks 1, 7 |
| Two bags on the same incoming edge | starts at ticks 1, 8 | ticks 1, 8 |
| Single bag, zero intermediate through | completion tick 28 | tick 28 |
| Single bag, one-second intermediate through | completion tick 33 | tick 33 |

All 8 cases passed; source admission remains tick 10 in the single-bag cases. The cross-port saturation interval changes from 1.0 to 1.2 seconds in the fixture. Its ideal service capacity is thus 16.7% lower than the parent's; equivalently the parent is 20% higher than V4. Whole-network throughput is not assumed to have that ratio. The same-incoming fixture reaches the service later for physical spacing reasons and is unaffected.

Reproduce only derivation, compilation and bounded fixtures:

```powershell
python scripts/eval/derive_feng_dh_next_tick_service_probe.py --verify
```

Full source/class identities, exact commands, test source hash and eight traces are under `outputs/runtime/feng_dh_semantics_reaudit_20260905/next_tick_service_fixtures`. The generator refuses to overwrite differing V4 sources and starts no full experiment. Full evaluation follows the [map2 protocol](feng_dh_map2_reaudit_protocol_20260905.md), comparing V4 with its parent on the identical 28,506-bag/43,603-leg shared-D population. Preserve the result regardless of the direction or closeness to historical numbers; source fidelity remains a separate question.
