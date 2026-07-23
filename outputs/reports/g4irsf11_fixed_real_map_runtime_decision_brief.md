# G4IRSF11 Fixed-Map Runtime Stop and GPT Pro Decision Brief

Date: `2026-07-23`

Branch: `codex/czr005-rewrite`

Decision authority: `GPT Pro`

Current handoff state: `STOPPED_AND_ARCHIVED_FOR_ARCHITECTURE_DECISION`

## 1. Executive conclusion

The fixed-real-map G4IRSF11 formal cohort is complete as an evidence cohort, but the current algorithm is not a capacity success. All `84/84` formal cases executed under one frozen implementation and map identity. The resulting gate status is `3 PASS / 3 PARTIAL_WITH_EXPLICIT_BLOCKER`.

The system-extension run was intentionally stopped at the user's request after `2/5` cases completed. The third case retains its original stale `RUNNING` descriptor and missing result; it was not rewritten into a synthetic failure or completion. Cases four and five never started.

The central finding is:

> The new event runtime satisfies the intended local-runtime invariants, but its present coordination and resource semantics collapse under the fixed real workload. It does not currently beat either the historical original-project result or the older v2-safe scheduling stack.

This report does not select the next architecture. It freezes the facts, defect hypotheses, and admissible options so that GPT Pro can make that decision. The current Codex runtime did not expose a model literally named `GPT Pro`, so no substitute model decision is claimed here.

## 2. Frozen evidence identity

| Item | Value |
| --- | --- |
| Formal cohort | `g4irsf11_fixed_real_map_parallel8_92c7e4588a90_run1` |
| Formal protocol | `g4irsf11-formal-2026-07-22-v4` |
| Expected / executed | `84 / 84` |
| Implementation SHA-256 | `92c7e4588a902770fd14ffd87c4924f7f7af9246a42b00dfc523616591e04ba9` |
| Implementation source-bundle SHA-256 | `99758e68f445d97c00b876e2edb788df2fdb51eb2443af42e9384b66ebd801e5` |
| Map path | `data/processed/maps/map2.json` |
| Map raw SHA-256 | `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4` |
| Map semantic SHA-256 | `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63` |
| Source path | `data/processed/tasks/inputdata.jsonl` |
| Source raw / semantic SHA-256 | `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f` |
| Source rows | `43,603` |
| Formal completion status | `COMPLETE` |

`COMPLETE` means that the predeclared evidence cohort and publication are complete. It does not mean that the algorithm passed its capacity, recovery, or service gates.

## 3. What the formal run proved

### 3.1 Gate result

| Gate | Status | Evidence boundary |
| --- | --- | --- |
| Paper-full event runtime | `PARTIAL_WITH_EXPLICIT_BLOCKER` | completion, queue stability, and service level failed |
| Fractional-frontier execution | `PASS` | `63/63` executed; all remained capacity-negative |
| Local safety/fairness ablation | `PARTIAL_WITH_EXPLICIT_BLOCKER` | `9/9` invariant-safe, but `0/9` zero-deadlock and `0/9` zero-starvation |
| Source-admission operational A/B | `PASS` | the switch changes counters and outcomes; capacity benefit is not proved |
| Temporal fault recovery | `PARTIAL_WITH_EXPLICIT_BLOCKER` | `0/5` cases recovered; `0/6` windows recovered |
| Real resource instrumentation | `PASS` | isolated-worker OS working-set measurements recorded |

### 3.2 Paper-full result on the fixed real map

| Metric | Result |
| --- | ---: |
| Raw bags | 28,506 |
| Complete raw bags | 3,114 (`10.92%`) |
| End-backlog / failed raw bags | 25,392 |
| Requested segments | 43,603 |
| Completed segments | 12,125 (`27.81%`) |
| Failed segments | 31,478 |
| Time limit | reached |
| Deadline miss rate | `97.30%` |
| Starved raw bags | 28,460 |
| Deadlocks / unresolved | 41,739 / 4 |
| Conflicts / runtime full A* | 0 / 0 |
| Original-entry p95 / p99 | 136,390 s / 144,999 s |
| Maximum wait | 274,068 s |
| Decision latency p50 / p95 / p99 | 4.4 / 14.6 / 25.0 microseconds |
| Maximum junction utilization | `0.1617` |
| Bottleneck node | 46 |

The decisions themselves are fast. The failure is not inference latency. Severe backlog coexisting with maximum measured junction utilization of only about `16%` is evidence of systemic idle/blocking behavior in the scheduling and resource semantics.

The successful invariants are still material: the runtime stored no future route, selected at most one next edge per `ARRIVE_JUNCTION`, used reservation depth one, made zero runtime full A*/CIE calls, performed zero global reservation scans, and recorded zero conflicts. These safety and locality facts must not be converted into a throughput claim.

### 3.3 Capacity and fault boundaries

- All `63/63` fractional-frontier cases executed and were safe, but all failed queue stability, service level, and capacity.
- The nine controller A/B cases accumulated `167` unresolved deadlocks and `640,069` starvation observations.
- All five temporal-fault cases executed, but recovery passed in `0/5`; all six repair windows remained `NOT_RECOVERED_BY_RUN_END`.
- The physical safety plane did work: unsafe physical-fault edge entry and physical-fault-window traversal remained zero. The recovery/capacity plane did not work.

Because the fault tests sit on top of an already unstable `2.5x` load, `0/5` recovery does not prove that every reroute action is useless. Recovery must first be retested at a stable load, then under overload.

## 4. Intentionally stopped extension

Extension cohort: `g4irsf11_fixed_real_map_extension_serial1_92c7e4588a90_run1`

Protocol: `g4irsf11-system-extension-2026-07-22-v3`

| Case | State at stop | Requested | Completed | Failed | Unresolved deadlocks | Boundary |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `extension_rolling_2day_full` | `EXECUTED`, rc=0 | 87,206 | 17,872 | 69,334 | 2 | time limit; capacity false |
| `extension_rolling_7day_full` | `EXECUTED`, rc=0 | 305,221 | 49,323 | 255,898 | 2 | time limit; capacity false |
| `extension_synchronized_8x_full` | stale `RUNNING` descriptor | 348,824 | n/a | n/a | n/a | intentionally interrupted; no result |
| `extension_synchronized_16x_full` | `NOT_STARTED` | 697,648 planned | n/a | n/a | n/a | not executed |
| `extension_fault_delayed_16x_full` | `NOT_STARTED` | 697,648 planned | n/a | n/a | n/a | not executed |

The third descriptor keeps run id `0ab9e5de-529a-4394-b989-48c0320b34bb`. Its recorded process and parent were stopped, no corresponding Python process remains, and no result artifact exists. Its stale descriptor and lock are retained as the truthful interruption record.

The completed extensions reinforce, rather than reverse, the formal result: continuity input audits pass, yet accumulated arrivals greatly exceed departures and capacity remains false.

## 5. What the historical comparison does and does not prove

| Stack / evidence | Complete bags | Reported mean | Important boundary |
| --- | ---: | ---: | --- |
| Original-project IoT-DRPA/HCA* text result | 28,506 / 28,506 | 3.967122711 min | parsed historical result; not a fresh headless Java/HCA* rerun |
| G4IRSF10 frozen v2-safe | 28,506 / 28,506 | 3.556593853 min | Java-release THT; older central replay/reservation skeleton |
| G4IRSF11 event runtime paper-full | 3,114 / 28,506 | survivor-only values are not comparable | current true event/local runtime; completion failed |

The frozen v2-safe number is numerically `0.410529 min` (`24.63 s`, `10.35%`) below the parsed original-project number in its accepted historical reporting path. That is valid historical evidence that the older stack was a strong engineering candidate. It is not a clean proof that a truly decentralized event runtime beat HCA*:

1. The original HCA* number is a parsed historical output, not a same-machine, same-executable rerun.
2. The v2-safe result uses `java_release_time_tth`. Recomputing the same candidate from original entry gives `4.124305453 min`; denominator choice materially changes the apparent comparison.
3. The older stack centrally iterates a task to its goal and writes successive future node windows into a global reservation structure. That scheduling skeleton supplies coordination that the new one-step event runtime deliberately removed.
4. The older candidate uses a trained small scorer and risk gate. The present event runtime uses a hand-written local score and has not trained v3. This is not a same-policy framework A/B.
5. The frozen v2-safe fallback was itself called `PIBT-lite`; it was not the repository's recursive multi-agent `PIBTStyleOneStepResolver`.

The accurate claim is therefore:

> The old v2-safe stack completed the fixed historical workload and produced a strong reported mean under its frozen denominator, while the current event runtime did not complete the workload. The evidence identifies a major regression after removing the old scheduling skeleton, but it does not isolate framework, policy, resource semantics, and metric denominator into a single causal variable.

## 6. Observed defects in the new framework

This section separates measured facts from hypotheses that require a new A/B.

### 6.1 The present controller is not the old trained decentralized policy

The current candidate ranking is a hand-written combination of static potential, travel time, immediate calendar wait, immediate queue pressure, and short-history penalties. The old frozen stack used a trained G4E scorer plus risk gating. A large share of the apparent framework regression may therefore include a policy regression.

Required diagnostic: run the event runtime with only legally available frozen-G4E local features, explicitly mark the model as out-of-distribution, and compare it to the current static scorer. This is diagnosis, not promotion evidence.

### 6.2 The old global coordination was removed without an equivalent local protocol

The new runtime correctly removed future routes and global reservation scans. However, the old scheduler's future node reservations implicitly serialized conflicting tasks and exposed downstream occupancy before arrival. The new runtime sees only local one-step calendars and beacons. No equivalent negotiation, credit, or multi-bag atomic arbitration currently replaces the lost coordination.

This is the architectural gap most consistent with low utilization plus extreme backlog.

### 6.3 Current `PIBT-lite` is only same-bag alternative scanning

In `cpp/ics_core/runtime/event_driven_junction.hpp`, lines around `1297-1311`, the fallback activates only after the top candidate is shield-blocked. It then scans lower-ranked candidates for the same bag and selects the first allowed edge.

It does not identify the owner blocking a target, inherit priority across bags, recursively move a lower-priority blocker, construct a simultaneous local action set, detect a wait-for cycle, or atomically commit/rollback a handoff chain.

Nevertheless, its ablation shows high leverage:

| Metric at 2.5x | PIBT-lite ON | PIBT-lite OFF |
| --- | ---: | ---: |
| Completed segments | 13,578 | 12,478 |
| Complete raw bags | 2,991 | 2,224 |
| End backlog | 68,158 | 68,925 |
| Total deadlocks | 70,649 | 103,018 |
| Unresolved deadlocks | 3 | 7 |
| Lite handoffs | 109,749 | 0 |

The lite mechanism adds `1,100` completed segments and `767` complete bags. Strengthening PIBT-like coordination is evidence-backed, but the remaining failure is too large to promise that PIBT alone fixes capacity.

### 6.4 Deadlock escape is retry-based, not cycle resolution

The runtime declares a bag deadlocked after eight retries and gives it a junction escape token. That token moves the bag to the front, but it does not move the resource owner that blocks it or resolve a wait-for cycle.

Measured ON/OFF behavior is mixed: completed segments are `13,578` with escape and `13,608` without; unresolved deadlocks are `3` versus `4`. The mechanism shortens some retry episodes, but it does not improve final bag throughput.

### 6.5 Backpressure has negative measured throughput contribution

| Metric at 2.5x | Backpressure ON | OFF |
| --- | ---: | ---: |
| Completed segments | 13,578 | 15,854 |
| Complete raw bags | 2,991 | 3,123 |
| Total deadlocks | 70,649 | 48,896 |
| Unresolved deadlocks | 3 | 2 |
| End backlog | 68,158 | 68,026 |

Turning the current pressure penalty off completes `2,276` more segments and `132` more bags while reducing deadlocks. The immediate pressure term is not capacity-calibrated and may create route oscillation or push traffic away from the correct short path.

The recorded two-hop pressure is diagnostic-only and does not affect ranking. One-hop/two-hop diagnostic A/B rows are consequently identical; the present controller does not obtain real multi-hop coordination from that field.

### 6.6 Source admission is operational, but its capacity benefit is unproved

| Metric at 2.5x | Admission ON | OFF |
| --- | ---: | ---: |
| Completed segments | 13,578 | 13,554 |
| Complete raw bags | 2,991 | 3,004 |
| Downstream-pressure holds | 1,103,628 | 0 |
| Beacon reads | 1,561,764 | 0 |
| Raw-bag source p95 | 1,418.0 s | 1.916 s |
| Unresolved deadlocks | 3 | 2 |

The switch now genuinely acts, which is why its operational gate passes. It adds only 24 segment completions, loses 13 complete bags, and shifts a very large wait upstream. It must not be reported as a capacity improvement.

The implementation uses a downstream beacon's single `service_calendar_reserved_until` value rather than an explicit expiring slot/credit. It admits when any outgoing edge looks ready, but does not bind that observation to the edge later selected. Repeated `0.25 s` polling generates million-scale attempts and holds. The formal setting `local_queue_capacity=0` means unlimited, so the configured-capacity part of downstream readiness is bypassed.

### 6.7 Corridor capacity semantics may be over-conservative

This is a high-priority code hypothesis, not a proven cause.

The event runtime merges `(u,v)` and `(v,u)` into one undirected corridor calendar and permits one reservation across the full travel interval. The older v2-safe scheduler primarily enforces node windows and treats edge overlap as diagnostic. If the physical system permits directed independence or multiple in-flight carriers separated by headway, the new corridor rule will suppress throughput sharply.

Do not simply disable the interlock. GPT Pro should require a legacy/physical-semantics audit and controlled directed-capacity/headway A/B before changing the safety rule.

### 6.8 Unlimited local queues hide missing buffer semantics

Formal runs use `local_queue_capacity=0`, meaning unlimited. A single junction reaches a queue near `36,400`. That is not evidence that a physical waiting location has sufficient capacity. Real buffer capacities must be extracted from authoritative project rules; otherwise this remains an explicit blocker.

### 6.9 Fault safety works, fault recovery does not

The physical interlock prevents unsafe entry, including when notifications are delayed or lost. But all recovery windows remain unrecovered and the fault-policy-off case can accumulate large physical holds. The next design must preserve the safety plane while redesigning the recovery/capacity plane.

## 7. Why the existing full PIBT-style resolver cannot be copied unchanged

The repository already contains a substantially stronger resolver in:

- `cpp/ics_core/baselines/pibt.hpp`
- `cpp/ics_core/baselines/pibt_replay.hpp`
- `src/czr005/baselines/pibt.py`

It provides deterministic slack/wait priority, current-node ownership, recursive priority inheritance, blocker movement, a visiting-cycle guard, and local node/edge/merge conflict checks.

However, it is not the frozen fallback that produced `3.5566 min`, and it is not directly admissible in G4IRSF11. The current C++ baseline resolver can call runtime A* for reachability and can read global reservation tables. Copying it unchanged would violate zero runtime full A*, bounded-local state, and no-global-reservation-scan requirements.

An admissible event-runtime adaptation would need all of the following:

1. Gather only simultaneously ready bags within a bounded local arbitration slice.
2. Preserve deterministic slack/wait/ready/task-id priority.
3. Track local blocker ownership and allow bounded recursive inheritance.
4. Use a strict handoff-depth limit and a visiting-cycle guard.
5. Use two-phase propose plus atomic commit/rollback for the local action set.
6. Commit at most one next edge per bag and keep reservation depth exactly one.
7. Replace runtime A* with frozen static reachability/potential metadata plus a bounded local trap guard.
8. Read only the relevant junction/corridor calendars and expiring credits, never a global reservation map.
9. Preserve the physical fault interlock in every proposed and committed action.

## 8. Decision options for GPT Pro

### Option A: tune weights and rerun the current runtime

Low confidence as the primary plan. Paper-full completes only `10.92%` of bags, current backpressure is net-negative, deadlock escape does not improve full-bag throughput, and the coordination gap is structural.

### Option B: keep the event runtime and add bounded local PIBT-style coordination

High-value candidate. The lite ablation provides direct evidence that handoff coordination matters. This option is admissible only if it follows the locality constraints in Section 7.

### Option C: redesign admission and backpressure as expiring local credits

Should be evaluated together with Option B, not postponed as a minor weight change. Credits need generation/version, expiry, hysteresis, fair allocation, and event-triggered wakeup. Source admission and the selected first edge must share a consistent resource claim or a safe invalidation rule.

### Option D: perform the corridor/buffer resource-semantics audit first

Mandatory before claiming capacity. Compare the current undirected capacity-one full-travel corridor with authoritative directed/headway/capacity semantics. Never obtain speed by silently weakening safety.

### Option E: connect the frozen old scorer to the event runtime as a diagnostic

Useful to separate policy regression from framework regression. Compare static scorer, frozen scorer, frozen scorer plus lite, and frozen scorer plus bounded PIBT. The old model is out-of-distribution and may use only already-audited legal local features; any win remains diagnostic.

### Rejected shortcuts

- Use the old full-route replay as a stuck-bag fallback.
- Restore global future-route reservations.
- Copy the old PIBT resolver while retaining runtime A* or global reservation reads.
- Train v3 before runtime/data gates pass.
- Hide failure with a smaller smoke workload, unlimited horizon, or topology change.
- Relabel cohort `COMPLETE` as algorithm `PASS`.

If GPT Pro chooses to continue the event architecture, the minimum coherent candidate is the combination of bounded local PIBT-style arbitration, credit-based admission/backpressure, and audited corridor/buffer semantics. Each component still needs an isolated A/B before the combined full protocol rerun.

## 9. Non-negotiable constraints for the next implementation

- Use only `data/processed/maps/map2.json` with the frozen raw and semantic hashes above.
- Do not mutate legacy Java, `map2.json`, or `inputdata.jsonl`.
- Do not generate, splice, or extend topology.
- Select at most one next edge at each arrival decision.
- Store no future route in a bag.
- Keep reservation depth one and diagnostic two-hop reads read-only.
- Use bounded local state; perform no global reservation scan.
- Keep runtime full A*/CIE calls at zero.
- Count source waiting in total-system-time reporting.
- Never disable the physical fault interlock.
- Preserve negative evidence and survivor-bias labels.
- Keep G4J closed until its separate boundary is accepted.
- Any implementation change requires a new implementation digest and a complete new formal cohort; current results cannot be reused as success evidence.

## 10. Archive checkpoint

Local checkpoint directory:

`C:\PROGRAMING\czr005\.local_archives\g4irsf11\20260723`

Primary raw checkpoint:

`g4irsf11_fixed_real_map_92c7e4588a90_formal84_ext2of5_stopped_20260723_raw_cache.tar.gz`

- Size: `738,306,161` bytes.
- SHA-256: `4929d5f3f49e4c7d35a640dcd8d158bd92eaa7f3b9b7ffd33b4c0e7f6b5fc80f`.
- `tar -tzf` verification: pass, `486` entries.
- Contains the formal workloads/results/descriptors/traces, completed extension workloads/results/descriptors, interrupted 8x workload/descriptor/lock, formal worker logs, and the older pre-fixed-map archive.
- Critical-entry checks passed for paper-full workload/result, both completed extension workload/result pairs, the interrupted 8x descriptor, formal worker logs, and the older archive.
- Four inaccessible stale `gate_a_production.pending-*` test-probe directories were excluded. They contain no declared evidence and are listed in the machine-readable stop manifest.

The corrected prompt and plan are copied beside the archive. The older archive is also retained separately for direct access:

- `pre_fixed_real_map_archives_20260722.tar.gz`
- Size: `377,743,091` bytes.
- SHA-256: `259758f590799641156491adb9079dfa31f2c69e0aaa586115cf50d65329fb00`.

The Git publication remains the durable lightweight record. The multi-hundred-megabyte raw checkpoints stay local and are ignored by Git.

## 11. Required acceptance sequence after GPT Pro decides

1. Freeze the chosen architecture and explicit resource semantics.
2. Add unit tests for simultaneous merge, blocked ownership chain, bounded recursion, rollback, source burst, and notification loss.
3. Run isolated A/Bs for scorer, PIBT, admission, backpressure, and corridor semantics.
4. Establish a stable-load recovery pass before overload fault stress.
5. Generate a new implementation/source-bundle digest.
6. Rerun the full fixed-map formal protocol with no smoke substitution.
7. Compare against the old v2-safe control and historical HCA evidence with denominator and scheduler boundaries visible.
8. Train v3 only after runtime, data, and promotion gates pass.
