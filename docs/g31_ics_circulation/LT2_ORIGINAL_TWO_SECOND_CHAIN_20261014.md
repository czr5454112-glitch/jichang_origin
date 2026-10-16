# Original two-second route-window investigation

The existing node112 feasibility failure remains authoritative: its actual1.5-second service window ended before the unchanged2-second route command arrived. This investigation uses a different path and preserves the original graph, closed edges, FIFO, capacities,22 trays, all28,506 input jobs and the separate symmetric research R1 permission.

`original_window_census_001` retains all4,001 jobs with an unreachable required stage, including2,124 with a pre-Storage leg and1,877 without a Storage contract. The latter remain in the original input and denominator. Eleven distinct pre-Storage source paths produce81 one-deviation alternatives:29 simple two-second ties,12 prefix-loop ties,29 simple1.5-second alternatives and11 prefix-loop1.5-second alternatives. The continuation is the unconstrained static shortest continuation after the requested next edge. It is never silently rerouted around a repeated prefix by adding unrecorded commands.

The saved native019 full-input prefix atH14400 contains106 sampled branch-node dwell windows,54 at nodes with1.5-second service. None of those54 is extended past two seconds by actual congestion. This does not rule out unsampled or later congested windows. Its first Storage53 head is unreachable bag0 at8430.351453; reachable bag2 enters at9033.022299, a602.670846-second gap. Bag0's single simple two-second deviations add78.04,79.54 or213.102 seconds in free flow, so none alone bridges this observed gap. Other unreachable jobs and the four later Storage entries are retained in the receipt diagnosis.

`original_tie_paths_001` then preregisters a bounded enumeration permitting choices only at nodes with service exactly2 seconds. Every1.5-second node follows its unchanged static default. Paths use only positive-capacity edges and cannot repeat any committed-prefix node. The budget is100,000 expanded states and50,000 terminal paths per source; candidate order is ascending-next DFS.

Bag0's0→53 domain **naturally exhausts** after99,932 states, yielding8,666 simple terminal paths and35,736 rejected cycle extensions. `independent_bag0_completeness.json` uses reverse distance labels and unbounded recursive enumeration: all8,666 paths are identical, there are zero missing/extra paths, and the producer's final stack is empty. The result did not stop68 states early with hidden pending work. Four other source domains reach the100,000-state cap and retain their explicit unknown frontier; the seven remaining source domains are complete.

Of bag0's8,666 paths,432 have estimated delay greater than602.670846 seconds. The predeclared fewest-command, then minimum-cost, then lexicographic rule selects four deviations:

1. At node1, request next2.
2. At node5, request next33.
3. At node33, request next51.
4. At node29, request next146.

The full static path is0→1→2→3→4→18→5→33→51→24→25→34→55→35→36→45→37→46→39→48→40→28→29→146→147→148→144→136→137→112→53. Its estimated extra travel/service time is613.034 seconds,10.363154 seconds beyond the observed gap. **This is an offline hypothesis, not a native arrival prediction or a full-suffix grant.** Live S4 resource arbitration can diverge at an uncommanded node. Each of the four commands must wait for the tray's actual local arrival, use that observed owner/generation/traversal, traverse the original2-second wire delay, pass native revalidation and produce the selected physical edge.

Native source ordering places E4 service completion before circulation wire/control-route events and junction arbitration after them. That suggests a two-second tie can be usable, but it does not replace native confirmation of the actual timestamp, owner, committed prefix and ACK. No source modification, telemetry reduction, pre-issued future-node command or physics pause is proposed.

`original_tie_chain_prepare_001` freezes one native feasibility branch. Its first1→2 command is the initial tie gate; remaining commands are conditional on delivered updated ACKs and the observed planned prefix. The branch stops at the first delivered rejection or path divergence, after all four selected edges and ACKs, or atH10000/activation/hard-time bounds.

`original_tie_chain_native_001` executed this branch on native019 with the same
28,506 jobs,22 trays and frozen source hashes. **All four commands received
delivered `updated` ACKs and produced their selected physical edge.** The actual
command execution epoch equals submission plus exactly2 seconds in every case.

| Route command | Current-local submission | Native execution / selected edge entry | Delivered ACK |
| --- | ---: | ---: | ---: |
|1→2|8278.810453|8280.810453|8281.010453|
|5→33|8356.760453|8358.760453|8358.960453|
|33→51|8375.870453|8377.870453|8378.070453|
|29→146|8727.682453|8729.682453|8729.882453|

The gate ended at physical8729.882453 after0.832204 seconds of worker control
time; `source_changed=[]`. It ends after the fourth edge, before the complete
planned path reaches Storage53. It establishes executability of these four
actual local decisions, not completed business benefit, full protection or a
100ms complete-request result. Its business metrics/gain remain null and
protection remains not assessed. This does not invalidate the earlier node112
rejection under its shorter1.5-second window.

`original_tie_comparison_prepare_001` separately freezes two matched full-input arms atH22200, admitted only after the same-input/same-binary native gate passes. Both receive the same permission and existing R2 forecast/predictive/prebalance continuation. The control keeps native R1; the candidate issues the four current-local commands. Both start from the same initial checkpoint, preserve all input, and run the physical audit. At this horizon3,998 jobs have arrived and24,508 remain future input; all28,506 stay in the accounting.

The mechanism question is whether actual bag2 Storage entry precedes bag0 and bag2 physically completes under the candidate, against the matched control. A positive mechanism result would still not certify full protection. Every unfinished-vs-unfinished completion difference, including bag0's, remains undefined; no zero or infinity is substituted. Known positive completion deltas fail protection immediately, while missing/unfinished comparisons prevent a pass. Censored arms remain unknown. Thirteen pure tests cover enumeration limits, causal local submission, actual-edge evidence, gate admission, denominator retention, strict known regressions and undefined unfinished comparisons.

The admitted pair in `original_tie_comparison_native_001` exhausted180 seconds
in **both** sequential arms. Both remain `unknown_hard_timeout`; there is no
complete native result from either arm. The receipt retains the full28,506
denominator and null gain, unknown Storage order and unknown individual
protection. Its empty `source_changed` list is not a completed-worker source
certificate because no completed arm supplied one. The separately saved
`post_timeout_source_observation.json` records unchanged files observed by the
parent after both workers exited, with that narrower scope explicit. A new
streamed comparison requires a new preparation and budget; it cannot relabel
these censored attempts as zero gain or reuse the fast gate as business evidence.

`original_tie_streamed_prepare_001` is the new four-branch registration. It first
compares candidateH10000 unbroken/public-copy execution with500-activation
shards/private-consume execution, requiring exact actual route requests, ACKs,
edges, ordinary calls/retries, controller state, physical results, initial/final
native seals and unchanged source. Only a pass admits the H22200 control and
candidate arms, each bounded by600 seconds and100,000 activations. All calls
request the same final physical horizon; a shard may retain an incomplete
timestamp for exact continuation. Every raw owner record, native boundary,
ordinary/injected call, checkpoint and route observation is saved; redundant
in-memory diagnostics are then released. Each boundary records an actual native
seal and its separate wall cost. GC remains enabled and callbacks are recorded,
so the suspected retention/GC bottleneck can be investigated without claiming it
was measured inside the previous censored workers. The archived native019 build
receipt binds the old binary to its build-time C++ hashes; current native023
sources are not substituted as its compilation authority. Twelve pure tests
cover the conformance admission, immutable shards and common-checkpoint guards.
This streamed registration has not executed yet.
