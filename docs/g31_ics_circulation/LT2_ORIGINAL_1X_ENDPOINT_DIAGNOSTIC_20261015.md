# Original 1x saved endpoint diagnostic

This is a diagnostic of the saved H=86400 endpoint, not independent acceptance of the entire run. No NativeSession was created. At this reading the producer was still publishing final artifacts; the separate full-run verifier was not used as an authority here.

The authoritative diagnostic is `outputs/experiments/g31_ics_lt2_sustained_20261014/full1x_endpoint_diagnostic_003/diagnostic.json` (SHA256 `3b7e6e25d9c7900527739e2d7c3572661baf56113ac60e544e5f1eb7087dc4c1`). It retains the exact analyzer, producer heartbeat and receipt snapshots. Versions 001/002 remain preserved. Version 003 additionally checks the subsequently published offline current-state export against all22 final trays and the exact seven outstanding wait identities, and maps its actual FIFO queues to jobs/trays.

## Bound source and scope

Only `full024_resumed_1x_20261015_001/segments/0450.json.gz` was read from the 451 raw shards. Its sidecar SHA256 is `7b42944de4b87b734e08ff51927c3336d11ccba40568f304cec0f78c3aac7b66`. The actual compressed input SHA256 is `d37118333de2aa60fb5e9b9d41bab53cccb7ddbab5842862b88a2818e08709a1` (28,506 jobs, 22 initial trays). The shard and contemporaneous heartbeat both contain native seal `2afe5ca1214a9a6fdd322700622eacbcfc589777af680cdd871ba2d0e1287475`. Equality of retained seal fields is checked; the seal was **not** independently recomputed here. Input, producer cut, actual native024 binary and three archived implementation headers are hash-bound in the report.

All 22 final positions were independently reconstructed from the initial tray positions and all 238 EDGE_ENTER/EDGE_EXIT pairs in this final cumulative result. There are 18 loaded trays, three empty-transit trays, one quarantined empty tray and **zero business completions**. The native summary's eight completed legs are not completed businesses. All final `edge_to` values are -1; the last observed edge exit was at 11318.812850000004.

## Current tray and business mapping

Business numbers below abbreviate `projected:1x:<number>`. All listed loaded jobs are still in transit.

| Node | Trays and carried businesses | Physical occupancy |
|---|---|---:|
| 53 | initial:0:0→0, initial:24:0→1, initial:26:0→2, initial:95:0→3 | 4/4 |
| 112 | initial:0:1→4, initial:24:1→5, initial:26:1→6, initial:149:0→9 | 4/4 |
| 29 | initial:49:0→8, initial:49:1→18, initial:92:0→14, initial:134:0→7 | 4/4 |
| 137 | initial:57:0→11, initial:57:1→19, initial:95:1→10, initial:136:0 empty transfer to24 | 4/4 |
| 28 | initial:92:1→15, initial:134:1→13 | 2/4 |
| 139 | initial:138:0 empty transfer to0, initial:138:1 empty transfer to24 | 2/4 |
| 150 | initial:149:1→12 | 1/4 |
| 136 | initial:136:1 quarantined empty | 1/4 |

Receiving leases additionally occupy one berth at0 and two at24. Native occupancy counts each tray once per node using the union of stationary position, incoming edge target and receiving lease. A moving tray's source position is not separately counted. The JSON includes all tray versions, active legs, transfer payloads/resolutions, latest lifecycle events, current suffix reachability and every outgoing receiver's occupants.

## A static witness, not merely a wait-graph cycle

Business0 on `initial:0:0` entered Storage53 and was released at19500. Its active storage-out leg requires destination99. At19500.751 the native receipt is `RESOURCE_WAIT:no_static_legal_suffix`. Independent positive-capacity graph closure from53 cannot reach99: the only boundary edge leaving that reachable set is97→98, whose declared capacity is0. The same mandatory destination makes loaded businesses1,4,7 and14 permanently unreachable under the fixed input and current loaded-carrier contract. A counterexample would be a positive-capacity directed path to99 in this exact input; changing that edge or destination would change the physical problem.

The actual offline wait subscriptions establish an upstream dependency chain: 28→29→112→53; 137,139 and150 also wait for112. The Storage53 native FIFO is exactly `[business0→99, business2→116, business1→99, business3→47]`, so the impossible business0 is the actual head, with reachable business2 and3 behind it. Its wait is explicitly `static_blocked:true` with no edge, receiving or ranking subscriptions. This is a concrete FIFO obstruction ending at an impossible destination, not a graph-cycle inference.

The other native FIFO business orders are28 `[15,13]`,29 `[8,7,18,14]`,112 `[4,5,6,9]`,137 `[10,11,empty136:0,19]`,139 `[empty138:0,empty138:1]`,150 `[12]`. At29,112 and150 the native wait also subscribes to policy-ranking changes at alternative successors; a simple graph that treats all these subscriptions as simultaneous physical blockers would be wrong. **No minimal resource cycle or general deadlock has been certified.**

The archived native024 `circulation_recovery_impl.hpp` records `no_static_legal_suffix` only after checking positive-capacity successor suffixes. Its resource subscriptions include receiver, edge and policy-ranking changes; treating them as an AND-dependency graph would be incorrect. `circulation_runtime_impl.hpp` also refuses a route preference without a static suffix to the current required goal. A112→113 diversion can change a berth dependency, but cannot create53→99 reachability or unload a trapped payload.

## Timed events and strategy implications

No final tray is on an edge or in loading/storage/unloading/hold mode; all original arrivals and listed fault/outage events are already accounted for. The actual offline export has zero scheduled incoming and no `next_dispatch_time` after86400. This excludes an immediate carrier lifecycle release visible in this endpoint, **not all future internal events**: the future native event heap is not exported. The empty tray at136 failed at11766.707600010008 because its departure lease expired before physical entry. It must not be classified as an unrecoverable loaded tray; an explicit legal empty-recovery operation is a different possibility.

The waiting112 gate remains a valid executability experiment in its separately declared R1-permitted research domain, but its success alone would not prove a business completion or protection. A startup R2 strategy must test whether it can preserve scarce empty carriers before unreachable FIFO heads load, without skipping those heads, adding trays, using future arrivals online or changing zero capacity. The separate 39/371 FIFO-carrier bounds are necessary relaxations, not executable plans.

Reproduce with `python -m scripts.experiments.g31_ics_circulation.diagnose_saved_full_day_endpoint --campaign outputs/experiments/g31_ics_lt2_sustained_20261014/full024_resumed_1x_20261015_001 --shard 450 --output <new-directory> --native-source outputs/experiments/g31_ics_lt2_sustained_20261014/native024_build_001/source`. The current analyzer SHA256 is `369908af8b28469a8bfe34ef69ae45c0585adcf3206d1f911b086560f5e19d98`.
