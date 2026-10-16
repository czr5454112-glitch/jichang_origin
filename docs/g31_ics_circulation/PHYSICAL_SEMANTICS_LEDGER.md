# LT2 physical semantics and necessary-bound ledger

Date: 2026-10-14. Scope: a read-only audit of the current source adapter, processed source map, native contract checks, and saved full-stream evidence. This audit did not regenerate business inputs, change physics, or run a native worker. It supplements [DATA_AND_MODEL_CONTRACT.md](DATA_AND_MODEL_CONTRACT.md); it does not replace the common research state or upgrade any research gate.

The original business stream is available. Unresolved items concern equipment semantics and operating contracts, not the absence of all business data. All bounds below are conditional on their named model and population.

## Source identity and population

The following two SHA256 values were recomputed in this audit and match the saved input manifests:

| File, relative to repository root | SHA256 |
|---|---|
| `legacy/jichang_origin_readonly/inputdata.txt` | `0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87` |
| `data/processed/maps/nanning_airport_profile.json` | `70aeeafe2c774d415fe9f922eedec36e8e35132bcba04596c2b1c486ffb3d1df` |

The current map contains 151 nodes and 227 directed edges. The retained source row for domestic `ICS103 -> ICS104`, map edge `97 -> 98`, records length 0.6 m, speed 2 m/s, and pallet capacity 0. Node 53 is `international:ICS54`, alias `IDK1`, type 7, role `empty_pallet_storage`; the source profile does not identify it as a confirmed baggage EBS. These fields were read directly from the current profile. The raw workbook/OOXML findings below are saved evidence, not a new workbook extraction in this audit. [Map profile](../../data/processed/maps/nanning_airport_profile.json), [saved source-row audit](../../outputs/experiments/g31_ics_long_term_20261013/p2_zero_capacity_semantics_001.json).

The full populations are 28,506 original simulated business bags and 57,012 bags under the existing complete-flight densification rule. Early-storage counts are 15,097 and 30,194. The doubled flow is derived from the same source, not a second independent operating day. Original task IDs, source lines, original OD namespace, projected OD, inserted identity and time shifts remain in the crosswalk. The original 54-node task namespace is distinct from the Nanning map namespace. [Adapter `build_input`](../../scripts/experiments/g31_ics_circulation/original_workload.py), [1x manifest](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_1x_prepare_001/input_manifest.json), [2x manifest](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_2x_prepare_001/input_manifest.json).

## Physical contract register

| Item | Original fields / established implementation | Explicit research interpretation | Unknown or unproved boundary |
|---|---|---|---|
| Zero-capacity link | Workbook 2 adjacency row 7 has numeric `F7=0`, no stored formula; the profile preserves edge 97 -> 98 and its direction, length and speed. All 227 profile counts equal `floor(length / 2 m)`. | Native positive-capacity routing treats capacity 0 as closed. The edge is retained, not silently deleted or raised to 1. | The numerical pattern does not establish whether a 0.6 m physical link permits continuous traversal with no whole-tray storage. That alternative needs explicit spatial/receiving semantics; it has not been implemented or validated. |
| EBS / Storage | Node 53 is an empty-pallet-storage source role. The inherited workload rule classifies early bags when `STD-arrival >= 4800 s` and declares `release=STD-2700 s`. | Node 53 is an explicitly named on-carrier EBS proxy: the same tray holds the same bag through storage and release. Storage release does not create an empty tray; an actual later unload and hold completion are required. | Real baggage EBS location, on/off-carrier policy, retrieval capacity, off-carrier bag storage and reassignment to a real receiving tray are unconfirmed. This runtime is not a validated off-carrier EBS implementation. |
| Berths and initial stock | Source edge pallet counts are retained. Native accounts for parked occupancy and receiving commitments; entered transfers keep physical identities. | Full-stream n4-s4-t2 runs use 4 ordinary and 4 Storage berths, 2 trays at each of 11 active loaders, total 22 trays. Earlier preparation manifests use Storage64; these are distinct contracts. Default headway is 1 s and post-completion hold is 1 s. | Node berth capacity, admissible loaded/empty waiting, actual inventory, headway and hold have no field calibration. `local_queue_capacity=0` in a runtime summary is not evidence for infinite physical berths; the circulation node contracts still constrain occupancy. |
| Service times | Source node service times remain in native execution. Type-7/11 missing service values in workbook 1 are the mature adapter's explicit zero imputation from corresponding types in workbook 2; native has a minimum service duration. | Extra adapter `load_seconds=unload_seconds=0` avoids charging additional duplicate service. Storage-in terminal processing and Storage-out source processing remain two transport-stage visits. | This does not prove one continuous physical EBS operation should be charged twice. No service carry-over or unverified equipment timing is inferred. |
| Fixed FIFO and routing authority | Runtime configuration requires S3/S4, FIFO, J2/E2 and learning off. Accepted stage goals, directed edges, entered prefixes and physical tray positions are preserved. | `research_r1_authorized` is a separate versioned permission to propose an uncommitted loaded suffix; it does not authorize bypassing a FIFO head, Storage, capacity or destination. Original24 remains a separate frozen negative control. | Research owner partitions do not establish physical distributed deployment or supplier controller authority. A blocked old route is not a valid fallback merely because it was previously selected. |
| Source reserve / module ports | Native checks an actual available empty tray, distinct source/destination logistics zones, `allow_export`, `allow_receive`, source stock strictly above `export_min_stock`, and destination occupancy before export. Analytic candidates additionally retain visible local FIFO demand before cross-zone export. | Full-map adapter sets port booleans true and `export_min_stock=0`; these values are declared proxy permissions. A same-zone endpoint pair is not authorized centrally even if its path crosses another zone. | Actual supplier module queries, internal balancing rules, export/receive authority and reserve levels are not established by these proxy defaults. Forecasts neither create stock nor grant export permission. |
| Normal-service protection | Native route acceptance rechecks business/tray identity, generation/traversal, stage reachability, received fault knowledge, entry feasibility and an optimistic deadline necessary bound. Post-run comparisons retain each offered bag and unfinished/deadline outcomes. | Paired `service_dominates` / protection reports establish only the named executed future and common horizon. Candidate pruning and visible-source stock retention are useful restrictions. | A deadline lower-bound check is not a completion guarantee. Neither aggregate improvement, meeting a deadline, `protected_service=true`, nor preserving a precommitted subset proves universal no-delay protection for all normal business, including waiting and unseen future bags. |

Exact implementation references: [ProxyContract and original adapter](../../scripts/experiments/g31_ics_circulation/original_workload.py), [native configuration, storage and export/route checks](../../cpp/ics_core/runtime/circulation_runtime_impl.hpp), [native contract types](../../cpp/ics_core/runtime/circulation.hpp), [analytic local-demand reserve](../../scripts/experiments/g31_ics_circulation/analytic_control.py), [full-population objective and paired protection](../../scripts/experiments/g31_ics_circulation/finite_reference.py), [independent protection assessment](../../scripts/experiments/g31_ics_circulation/assess_joint_window_protection.py).

## Saved necessary bounds and their limits

| Evidence | Actual saved result | Valid inference | Inference not supported |
|---|---|---|---|
| Full-flow static positive-capacity path diagnostic | 4,001 / 28,506 unreachable at 1x; 8,002 / 57,012 at 2x. No additional deadline-infeasible reachable bag under the capacity/queue-relaxed calculation. | With these unchanged stage goals, directed graph and closed-zero interpretation, topological completion ceilings are 24,505 and 49,010, before finite-tray congestion. | Reachable does not mean schedulable or protected. A zero additional deadline count is not a guarantee. Changing zero-link semantics changes the premise. |
| Build005 fixed-state blocking certificate | All 13 listed conditions hold. Storage53 FIFO `[22,23,24,25]` occupies its 4 berths; head bag `projected:1x:0` has unreachable goal 99. The other 18 loaded trays require that same Storage. Actual receiving chains terminate at it; no empty/in-flight/recovering tray or receiving lease is available in this saved state. | Under fixed FIFO, on-carrier occupancy, unchanged goals/capacities, zero-as-closed and no unauthorized unloading/cancellation/tray creation, this state cannot produce a completed bag or usable empty tray. | This is a sufficient state-specific dead-end certificate, not a claim of a circular wait, airport-wide impossibility, or a theorem for later runs with in-flight trays/leases. Do not apply it to a changed state without rechecking all conditions. |
| Separate 24-bag, one-tray FIFO lower bound | Saved bound requires at least 19 deadline misses; the analyzed completed branches have 19. | That single-tray, single-loader, distinct-arrival, fixed-FIFO on-carrier domain cannot remove all 19 misses by legal same-order routing alone. | This is not a full 1x/2x or multi-tray lower bound. A gap above an optimistic bound is not demonstrated attainable improvement or a learning label. |

Sources: [1x static diagnostic](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_1x_prepare_001/static_diagnostics.json), [2x static diagnostic](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_2x_prepare_001/static_diagnostics.json), [fixed-state certificate](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_offline005_001/fixed_contract_blocking_certificate.json), [certificate implementation](../../scripts/experiments/g31_ics_circulation/certify_original_blocking.py), [single-tray bound receipt](../../outputs/experiments/g31_ics_long_term_20261013/p4_single_tray_lower_bound_006_002/receipt.json). These saved calculations were inspected here, not rerun. Arrival-to-release time is explicitly not an unconditional Storage occupancy lower bound: loading may legally occur later.

## Saved complete-flow executions, distinct from LT2 reruns

These two historical analytic reactive runs reached H=86,400 s with the complete business population. They use different native builds, so their wall times are not a same-build speed comparison. The native summary's completed transport-leg count is not a completed-business count.

| Historical directory | Build / offered and observed | Loaded / completed business | Final trays | Audit and censoring |
|---|---|---|---|---|
| `p2_original_1x_reactive_compact_H86400_007_001` | 007; 28,506 / 28,506 | 18 / 0; 28,488 waiting | 18 loaded, 3 empty-transit, 1 quarantined; 3 receiving leases | Audit passed, 210 complete traversals; horizon reached, no event-budget censoring; one `departure_lease_expired_before_physical_entry`. |
| `p2_original_2x_reactive_compact_H86400_010_001` | 010; 57,012 / 57,012 | 17 / 0; 56,995 waiting | 17 loaded, 4 empty-transit, 1 quarantined; 4 receiving leases | Audit passed, 192 complete traversals; horizon reached, no event-budget censoring; one `departure_lease_expired_before_physical_entry`. |

The matched n4-s4-t2 input hashes are `d9e065f51c4eb056e18fdbc7abb7dcacec938ff1e1e38010101de751ad52a30d` (1x) and `1e263518b6c82cbeba384a3854a727dc1e3914212e58811ee37bd5ee6665d122` (2x). Exact results and build identities: [1x summary](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_1x_reactive_compact_H86400_007_001/summary.json), [1x receipt](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_1x_reactive_compact_H86400_007_001/receipt.json), [1x audit](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_1x_reactive_compact_H86400_007_001/event_audit.json), [2x summary](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_2x_reactive_compact_H86400_010_001/summary.json), [2x receipt](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_2x_reactive_compact_H86400_010_001/receipt.json), [2x audit](../../outputs/experiments/g31_ics_long_term_20261013/p2_original_2x_reactive_compact_H86400_010_001/event_audit.json).

These are complete-horizon business failures under declared research contracts. They do not show that all bags are individually topologically impossible. Successful identity/capacity replay verifies execution integrity, not business success or normal-service protection. Earlier H=21,600 comparisons and budget-censored runs remain separate evidence and must not be relabeled full-day results. Historical owner-subchain timing does not certify the complete request <=100 ms requirement.

## LT2 native016 full-input prefixes

The two new runs below use the same n4-s4-t2 proxy, reactive event protocol,
native016 SHA `af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0`,
and H=86400. Both stop at the declared 2,000 owner-activation budget. Their
worker exit codes are 0, but their physical campaign status is
`control_budget_exhausted`; neither is a completed full-day result.

| New run | Full input population | Physical stop | Actually offered by stop | Requests / unresolved | Business completion metrics |
|---|---:|---:|---:|---:|---|
| [full1x prefix](../../outputs/experiments/g31_ics_lt2_20261014/request_profile_full1x_001/summary.json) | 28,506 | 14715.27765 | 201 | 167 / 3 | unknown: no complete H result |
| [full2x prefix](../../outputs/experiments/g31_ics_lt2_20261014/request_profile_full2x_001/summary.json) | 57,012 | 13018.488280000001 | 143 | 126 / 5 | unknown: no complete H result |

All future input jobs remain in the saved input. Only arrivals up to the
actual physical clock belong to the observed prefix denominator. Do not
convert these censored runs into 0/28,506 or 0/57,012 completed-day failures,
or reuse older native-version completion metrics for them. Failed/rejected
and unresolved protocol requests remain in the accounting. Each directory
contains source/binary hashes, raw input, raw run, stdout/stderr and the
actual worker exit code. Complete-request timing and per-job protection
remain unverified for these prefixes.

The unresolved field contracts block field interpretation and final business certification. They do not prevent bounded same-contract online experiments, genuine R1/R2 coupling analysis, strong-reference diagnostics, or complete-request profiling.

Additional LT2 joint-policy runs retain the same 28,506 input population.
`request_profile_segmented_full1x_001` hit its 120-second hard timeout;
only complete saved segments through 10,800 s (22 arrived, zero completed by
that prefix) are reliable. Its unsaved tail and full-day outcome are unknown.
`request_profile_indexed_full1x_001` completed the declared 2,500-activation
budget at 10,995.837986 s (23 arrived), retaining 570 request IDs including five
open requests. Its full-day metrics are null. Neither prefix resolves field
semantics or replaces the historical complete-day negatives above. Their
joint policy differs from the earlier reactive prefixes, preventing a direct
speed comparison. Details and source-bound receipts are linked from
[the LT2 progress record](LT2_PROGRESS_20261014.md).
