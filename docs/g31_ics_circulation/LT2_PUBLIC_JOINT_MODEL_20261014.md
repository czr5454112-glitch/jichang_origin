# Conditional public joint model and all-117 validation

The pure model selects a joint initial loaded route and empty departure time from captured local information, without native forks or an outcome table. In the saved synthetic domain, its selected actions are protected in all three gate regimes. This is a useful **offline B3-style finite joint reference**, but it is not an online controller, a complete rolling MPC baseline, or a certified protection model.

## Inputs and implementation

`scripts/experiments/g31_ics_circulation/public_reuse_model.py` accepts a common static contract, immutable canonical captures from A and B, and an action. It has no native session, checkpoint, native result or branch-label input. The offline evaluator alone loads the saved native labels after writing predictions and proposals. The candidate generator uses public durations plus the source-local loaded timestamp: 31 fixed-route departure times and four route2 times, totaling 35 actions per regime. It does not use the observed winning action to construct these times.

The model represents two distinct trays and all four current service obligations. It includes receiving leases acquired at grant, incoming occupancy before physical arrival, physical node capacity, edge capacity and entry headway, shared non-goal service calendars, FIFO waiting, loading/unloading/hold, mandatory on-carrier Storage, two actual L return/reload cycles, transfer ACK sampling/retries and rejection recovery, and the same delayed forecast continuation. It projects the native R3 resource and E4 event semantics; physical execution remains exclusively native.

The current supported checkpoint is the stationary time0.11 fixture. Missing counterpart, missing job/resource coverage, an unexplained occupancy reservation, a future observed epoch, stale capture, in-flight tray, known fault or unsupported state returns unknown. Public future contract values such as a Storage release gate are distinguished from future observed timestamps. A capture with caller-supplied `native_delivered_planning_contract` provenance does **not** verify native delivery: the verified online flag remains false, with declared metadata recorded separately. A trusted future adapter must validate the actual native envelope, capture/delivery order, static identity and exact sender self-copy.

## Full validation, including errors

Evidence: `outputs/experiments/g31_ics_lt2_sustained_20261014/public_model_004/`. It contains preregistration, frozen source copies, capture bundles, predictions, proposals and per-cell residuals for every one of the 117 v2.1 native branches. No additional native branch was run for model validation.

The first projection, retained as `public_model_001`, matched 102 completion vectors exactly, but had a maximum error of3.501seconds and missed one protected action. Two errors were traced to native source rules: E4 circulation grant events precede junction dispatch at the same timestamp, and R3 excludes a goal's service from the shared destination calendar while retaining its receiving berth capacity. These are implemented in the second model version. `public_model_002` preserves that intermediate validation; 003 adds metadata guards and separate proposal timing. Final004 additionally rejects unsupported export/receive/min-stock contracts, unexplained available stock, delayed initial E availability and wrong-owner tray captures; all valid physical predictions remain unchanged.

Final results:

| Check | Result |
|---|---:|
| Native branches retained and compared |117/117|
| Individual completion residuals |468|
| Exactly equal completion vectors |105/117|
| Remaining completion error |12 loaded-job values underestimated by about1ms|
| Mean absolute completion error |0.000025641seconds|
| Maximum absolute completion error |0.0010000000000012221seconds|
| Later executed route edges matched |117/117|
| Terminal receiving rejection counts matched |117/117|
| Strict protection classifications matched |117/117:20 protected,97 unprotected|

The residual1ms is retained rather than absorbed into the zero-degradation test. An empirical maximum error on this finite set is not a deterministic error bound for future inputs. Model protection and native protection are separate fields. The model never certifies the latter.

| Gate | Model-selected action | Native gain against declared route1/window1 incumbent | Gain against stronger fixed-route timing reference |
|---|---|---:|---:|
|0|route1, departure2.201|0.009seconds|0|
|6|route2, departure0.11|1.410seconds|1.401seconds|
|12|route1, departure0.11|2.090seconds|0|

All three selections match previously executed native actions and pass strict protection for every offered job. This is offline evaluation of the model's choices, not evidence that either online owner already possessed the combined captures. The later feedback causal boundary from the v2 study remains: the protected gain does not depend on adaptive later bypass; the0.81-second forecast benefit occurs only in protection-failing cells.

The 35-candidate model-only proposal calls took about72–75ms in the final diagnostic. This excludes capture, communication, validation, action submission and terminal ACK; it does not satisfy or estimate the complete-request100ms requirement.

## Smallest missing communication for this fixture

The existing demand messages already carry affected job IDs, origins, arrival order and deadlines; public graph/resource contracts and receiver loading duration3 are shared. A typed source-captured extension only needs the **affected current obligations**, not all remote future work:

- A→B: loaded L's destination, mandatory Storage node/release/minimum dwell, unloading and hold durations; receiver's destination and unloading/hold durations.
- B→A: reuse1/reuse2 destination and loading/unloading/hold durations, keyed to the already delivered demand identities and FIFO order.
- Source-local current tray identity, node/mode/job, generation/traversal, edge/reception fields, and local committed service readiness. Existing native service-forecast capture already computes local service readiness; it is not an oracle of future congestion.
- Explicit affected-job/tray/resource coverage, source capture identity/time, actual delivery time, expiry, static digest and exact sender self-copy. Owner-local resource observations must remain source-authorized.

At this initial fixture all trays are stationary and accounted for, so incoming occupancy can be checked against the complete two-tray population. A later rolling invocation with uncertain reservation clearance requires conditional intervals or unknown results for dependent actions. The current pure model rejects those unsupported later snapshots; it does not request hidden future state or infer zero occupancy from an omitted field.

Positive publication delay must be paid. An online experiment can capture at an earlier lawful event and validate aged state at its decision, or move the decision and all controls. It cannot relabel the saved time0.11 snapshots as already delivered. Actual typed delivery, a later-checkpoint projection, matched online controls and full-request accounting remain implementation work.

## Tests and scope

`tests/test_g31_circulation_public_reuse_model.py` has23 passing tests covering immutable inputs, fabricated provenance, source authority, missing/stale/future state, receiving-lease timing, E4 grant ties, resource waits, closed-edge unknown, two reuse cycles, candidate purity, strict positive-delta rejection, and the full117 saved native comparison. `public_model_tests_002.xml` records the run. The separate v2 continuation suite has22 passing tests in `reuse_v2_tests_002.xml`.

This discrete reference is inspired by the rolling joint routing/empty-management baseline discussed in `LT2_CONTINUED_METHOD_SOURCES_20261014.md`; it is not a literal reproduction of the continuous-flow paper formulation. No B4 completion, novelty, continuous optimum, original-map efficacy or full-scale completion claim follows from this diagnostic.
