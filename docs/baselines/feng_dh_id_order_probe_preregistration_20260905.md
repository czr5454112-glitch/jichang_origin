# DH grant-order probe: pre-result contract, 2026-09-05

This note was written after bounded mechanism fixtures and before either task-id probe's full map2 result. The independent variable is the grant priority of bags already eligible for a common node-through service or target-edge entry. No historical mean, G31 comparison, or partial-population performance was used to choose the priority.

The English CIE revision, PDF pages 25–26, and the reviewer response, body paragraph 111, describe updating bags “one by one.” Their complete source identities and the Chinese wording difference are recorded in [the primary-source audit](feng_dh_primary_semantics_reaudit_20260905.md). This motivates testing traversal-related grant priority. It does **not** establish the original container type, traversal order, visibility of in-place changes, fairness policy, or whether (a), (b), and (c) are separate whole-population passes. Ascending generated task identity is a hypothesis, not recovered Feng source behavior.

Both probes remove only the arrival-tick and release-tick prefixes from `entryOrder()` and `nodeServiceOrder()`. Their order becomes ascending `taskId`, then incoming edge ID. The benchmark encodes task IDs from raw-bag identity and segment identity (`rawBagId * 2 + segmentId`). Scientific METHOD labels also change. Movement planning, snapshot timing, candidate paths, score coefficients, source release/induction, EBS legs, transfer timing and physical storage remain byte-identical to the respective parent outside those comparator bodies and labels. Inherited FIFO wording in surrounding comments describes the parent and is superseded by this explicit probe contract. This is **not** a full asynchronous simulator.

| Probe | Parent physical contract | METHOD | Source aggregate SHA-256 |
|---|---|---|---|
| `feng_cie_dh_overlap_id_order` | Repaired/optimized off-edge overlapping transfer | `FENG_DH_OVERLAP_ID_ORDER_V1` | `2b737ed71f96bf0fb08afdb5009de6eecb36ca9d81edbef74b2586ab1846de54` |
| `feng_cie_dh_retained_boundary_v2_id_order` | Frozen upstream-retained transfer V2 | `FENG_DH_RETAINED_BOUNDARY_ID_ORDER_V2` | `6ce227da2fb98876f3a6061e034b24996a0fee8b8510372bc6f61a77c396095d` |

The five source files use CRLF. Aggregates use the external identity gate's sorted relative-name and content length-prefix convention. The derivation manifest records each parent and derived file hash; only Simulator and Benchmark differ. Parent source and classes are unchanged.

The node-service fixture has two contenders arriving at ticks 1 and 2 via distinct incoming ports while a third bag occupies the common one-second service. The earlier contender has raw ID 10 (task 20); the later has raw ID 1 (task 2). FIFO starts them at ticks 6 and 11, while task-id priority reverses those grants in both physical contracts. These arrival times arise from normal movement, without rewriting timestamps or reflective state injection.

The entry fixture has two contenders that have both completed their zero-through and two-second transfer stages before a blocked outlet opens. Physical arrival again opposes identity order. The off-edge parent grants the earlier and later bags at ticks 21 and 42; its probe reverses them. The retained parent grants them at ticks 31 and 62; its probe reverses them. Every fixture checks lattice integrity, unique physical ownership and eventual completion after each tick. All eight parent/probe cases passed. These fixtures prove the intended priority mechanism changes; they do not establish historical fidelity or population-wide benefit. Persistent task-id preference could disadvantage newer bags under continuing demand, which must be visible in full-population completion and tail statistics.

Reproduce derivation and bounded fixtures from the worktree root:

```powershell
python scripts/eval/derive_feng_dh_id_order_probes.py --verify
```

Evidence: `outputs/runtime/feng_dh_semantics_reaudit_20260905/id_order_fixtures/derivation_and_fixtures.json`, per-version results JSONL and two complete event traces. Isolated build: `build/feng_dh_id_order_probes`. The generator refuses to overwrite differing derived Java and never launches formal experiments.

Full evaluation uses the separately registered [map2 protocol](feng_dh_map2_reaudit_protocol_20260905.md): identical map, input and shared-D schedule identities; all 28,506 raw bags and 43,603 legs; raw THT as the sum of leg completion minus scheduled release; completion, distribution and signature review before any extension. Compare each task-id probe to its own FIFO parent. Report both results regardless of closeness to the historical target. A numerical match alone cannot identify original execution semantics.
