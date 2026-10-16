# Original-flow head-arrival interference: feasibility gate

Status: native019 feasibility gate executed; its first route intervention was rejected and the business comparison was not admitted. The driver is `scripts/experiments/g31_ics_circulation/research_original_interference.py`. `original_interference_prepare_003` preserves the preregistration, input and permission manifest; earlier preparation artifacts remain unchanged.

The prior 99 R1 branches do not test this mechanism. Their 32 isolated one-job/one-tray contexts use the first 16 jobs for which **every required stage is reachable**. They explicitly exclude the 4,001 jobs with an unreachable required stage, including `projected:1x:0` (origin0, mandatory Storage53, destination99). Their observed negative benefit does not falsify reordering a blocking unreachable head relative to another tray.

The saved build005 certificate has bag0 at the Storage53 FIFO head and reachable bag2 behind it. Both have release gate19500 and deadline22200. Under that unchanged input, the source-predeclared simple path avoiding bag0's executed prefix needs three native next-hop preferences:112→113,141→145,35→11. Its static service/travel total is782.798seconds, giving nominal Storage arrival9050.644453. The saved control bag2 arrival is9033.022299, a17.622154-second ordering margin. A single112→113 request is insufficient: subsequent native shortest routing returns through112 with total503.408seconds, well before bag2. The three preferences are therefore part of one hypothesis, not three interchangeable alternatives.

Even though both arrivals precede gate19500 by a large margin, arrival order can matter: native Storage-release events are scheduled when each tray enters, and the tied release queue preserves that event order. The proposed route program aims to change the actual arrival/release order without modifying FIFO. It cannot make goal99 reachable and cannot establish full business completion.

## Unchanged communication exposes a feasibility barrier

| Required source | Normal service window | Command delay | Margin |
|---|---:|---:|---:|
|112|1.5s|2s|−0.5s|
|141|1.5s|2s|−0.5s|
|35|2s|2s|exact timestamp tie|

In saved build005, bag0 physically reaches112 at8359.100453 and commits112→53 at8360.600453. A request from the earliest destination-owner local observation would execute at8361.100453. Node29's owner differs from node112's owner; native tray visibility is filtered by its current node's owner, so the destination owner does not have an earlier local tray identity while it is incoming from29. This driver does not fabricate a remote generation, pre-issue a future-node command, shorten the delay or pause physical time.

These timings are a source/old-state screen, not an outcome on build019. Live contention could lengthen a service window. The first native probe therefore retains the full original input and the fixed two-second delay, advances through actual owner-notification boundaries, submits the observed current identity, and records the delivered ACK plus owner-visible actual edge. It stops at the first delivered rejection. An unexpected acceptance permits continuation through the other two declared preferences; all three updated ACKs and all three actual selected edges are required before admitting the business comparison.

The feasibility gate has one native branch. Only if it passes are two same-checkpoint, same-permission H22200 comparison arms admitted. Both retain all28,506 jobs,22 trays, fixed FIFO/capacities/Storage/contracts and identical event-based R2 continuation; automatic R1 is disabled in both, with only the candidate's declared program added. A180-second process timeout preserves incomplete artifacts. The gate stopped on its first rejection, so neither comparison arm ran.

If the gate rejects, the two arms become `not_admitted`; business metrics and gain remain null. If comparison proceeds, all input obligations remain in the common-horizon denominator, including unreleased and unfinished jobs. Individual zero-degradation is unknown if any offered completion is unfinished in either arm;−1 is never used as a real completion time. A physically completed bag2 can establish the stated prefix mechanism, but not full-day or all-business protection. Source drift invalidates the claim.

Twelve pure tests pass in `original_interference_tests_003.xml`: original population/permission preservation, unchanged delay screen, local source/stage/generation guards, delivered-ACK ordering, retained stale rejection, missing-arm denominator handling, and ACK-plus-actual-edge admission. The full-day permission-false original-flow experiment remains a separate immutable negative case.
# Native019 feasibility result

`original_interference_native_001` executed the preregistered gate with all 28,506 jobs and 22 trays. At native time 8359.100453, the domestic owner observed bag0 at node112 and submitted the 112→113 intent with the unchanged two-second delay. Native execution at 8361.100453 rejected it as `stale_executed_prefix`; its ACK was delivered at 8361.300453. The gate stopped there. Source hashes were unchanged.

Both H22200 comparison arms are `not_admitted`; business metrics and gain are null and strict protection is `not_assessed`. This is an executable intervention failure under the declared local observation and communication contract, not a zero-benefit performance result or a general impossibility theorem. The native receipt and complete local observation/intent/ACK are saved in `outputs/experiments/g31_ics_lt2_sustained_20261014/original_interference_native_001/`.

