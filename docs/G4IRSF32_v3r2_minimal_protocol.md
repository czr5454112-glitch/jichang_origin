# G4IRSF32 V3R2 minimal source-aware destination-service protocol

Protocol ID:
`G4IRSF32_EXTERNAL_COMMIT_LOCAL_VIRTUAL_SLOT_SHADOW_P0_STAGE0_STAGE1_V3R2`

Implementation parent and audit base:
`46cc46ab6bc121628fd6357e9f3c7636745fd732`.

Frozen `2026-08-27` (Asia/Shanghai), before V3R2 implementation or data.
Status: `FROZEN_PROTOCOL_ONLY_NO_V3R2_DATA_RUN`.

Unless a raw-file hash is named, "canonical compact JSON" means UTF-8 bytes
from `json.dumps(value, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` with no trailing newline.

V3R2 keeps the V3R1 external-commit/local-virtual-slot estimand, but closes
two pre-run audit defects: V3R1 hard-coded the synthetic storage node `[0]`
and therefore could not execute the required map2 sentinel, and its provisional
runner inspected the generic decision-trace schema key instead of the
namespaced G32 schema key. No V1/V2 implementation, output, or test is part of
this clean branch.

## 1. Scope and complexity budget

This is P0 shadow only. It changes no route, action, calendar reservation,
event, grant, completion, S4/J2/E2 decision, or G31 result. A GO only permits a
separately frozen P1 action review.

The only formal modes are `off|shadow`; all other strings fail closed. The
default is `off`. The implementation may add one numeric fixed-layout row,
summary counters, one bounded result-sidecar vector, and pure calendar helper
arithmetic. It must reuse the existing bag, junction, source queue, calendar,
DIRECT dispatch, and J2 exact-reservation authority. It must not add a policy,
model, arbiter, runtime event, per-node/per-bag registry, route suffix, future
route, map-specific node branch, V1/V2 compatibility mode, or disabled dead
code block.

Production changes are limited to the existing event runtime, pybind surface,
and Python backend. Experiment-only code is limited to one outcome join, one
runner, their focused tests, this protocol, and new evidence outputs. The final
diff is audited against the implementation parent; rejected V1/V2 code and
historical outputs must not be copied into this branch.

The hook may inspect only the destination node's existing local controller,
the committing external bag/request, the existing source queue winner, and the
destination service calendar. It must not scan all bags/tasks, inspect future
releases, read two-hop state, run A*, call a model, or branch on map identity.

## 2. Frozen profiles, requests, and populations

### 2.1 Synthetic Stage 0/1 motif

For `s in {1.0,1.5,2.0,3.0}`:

- nodes `(id,type,service,x,y,outgoing)` are
  `(0,7,0,0,0,[1])`, `(1,1,s,1,0,[2])`,
  `(2,4,0,2,0,[3])`, `(3,2,0,3,0,[])`;
- edges `(from,to,length,speed)` are
  `(0,1,0.05,1.0)`, `(1,2,0.05,1.0)`, `(2,3,0.05,1.0)`;
- starts are `[0,1]`, goals `[3]`, storage sources `[0]`, and L is node 1;
- deterministic service-aware potential uses minimum service `0.001`.

The J2 Stage 0 fixture adds node `(4,7,0,0,1,[1])`, edge
`(4,1,0.05,1.0)`, and start/storage node 4. The distant-state fixture adds
the disconnected directed chain 10 -> 11 -> 12 exactly as specified in
section 5.

### 2.2 Complete shadow request projection

Only mode, scenario, rows, graph/profile, storage-role list, potential, and
resolved binary path vary between frozen cases. All shadow cases use:

```text
queue_discipline=fifo; retry_interval=0.25
minimum_service_seconds=0.001; dispatch_headway_seconds=0.001
history_limit=8; max_decisions_per_bag=512
max_events=2000000; max_simulation_time=-1
trace_limit=200000; event_trace_limit=200000; summary_only=false
trace_shard_count=1; trace_shard_index=0
local_queue_capacity=0; deadlock_retry_threshold=8; diagnostic_hops=2
enable_source_admission=false; enable_backpressure=false
enable_pibt_lite=false; enable_deadlock_escape=true; enable_fault_policy=true
fault_windows=[]; scale=1.0
resource_semantics=R3_java_node_window_compatible
entry_headway_seconds=0.001; pressure_mode=off
pressure_weight=2.0; pressure_age_weight=0.05; pressure_distance_bias=0.25
admission_mode=off
credit_validity_seconds=1.0; credit_snapshot_max_age_seconds=1.0
credit_capacity_per_edge=1; credit_lifecycle_limit=512
pibt_mode=P2; pibt_max_depth=2; pibt_max_ready_bags=8
pibt_max_local_resources=32; pibt_max_candidates_per_bag=8
priority_mode=Q0; pibt_preference_mode=current
pibt_regret_prior_records=[]; selective_credit_contention_threshold=1
scorer_mode=S4_queue_aware_rule_only; scorer_model_path absent
framework_mode=event_loop_one_step
event_semantics=E4_batch_plus_destination_merge_request
merge_grant_rule=M3; merge_grant_timing_mode=jit_fair_aging_deadline
merge_grant_max_pending_requests=256; merge_grant_lifecycle_limit=8192
g4irsf20_event_hotpath_policy=E2; g4irsf16_supervisor_mode=off
enable_opportunity_telemetry=false; opportunity_trace_limit=0
enable_s4_local_potential_descent_guard=true
enable_s4_direct_neighbor_merge_calendar_visibility=true
complete_on_goal_arrival=true
source_aware_destination_service_mode=off|shadow
source_aware_destination_service_trace_limit=200000
```

`storage_source_nodes` must be an explicit, nonempty, unique subset of the
declared start nodes. It is `[0]` for the motif and `[52]` for the frozen map2
sentinel. Neither C++ nor Python may contain a map-ID/node-ID policy branch;
the runner binds the complete profile and role-list hashes. Closed-loop,
learned, causal, model, DLP, and legacy observation-bias inputs are forbidden.

### 2.3 Fresh synthetic population

The formal Stage 1 population is the Cartesian product of four services,
populations `{8,32,128}`, and these ten flows, in listed order:

`external_only`, `local_only`, `simultaneous_local_first`,
`simultaneous_external_first`, `local_burst_first`,
`external_burst_first`, `alternating_local_first`,
`alternating_external_first`, `local_backlog_external_sparse`,
`external_backlog_local_sparse`.

Controls contain one origin. Mixed flows contain `n/2` of each origin.
Simultaneous releases are 0; burst second halves release at `0.25*s`;
alternating pair k at `0.20*k*s`; backlog `3n/4` at `0.05*k*s` and sparse
`n/4` at `1.50*(k+0.5)*s`. Origin swaps preserve release multisets.

Case order is service, population, then flow. Case ID is
`v3r2_{flow}__n{n}__service_{s_with_p_decimal}s`; scenario prefixes it with
`g4irsf32_v3r2_`. For zero-based case/bag ordinal,
`task_id=32032000+128*case_ordinal+bag_ordinal`. External start is 0, local
start 1, goal 3, deadline `max_release+n*s*10+100`, and segment ID is
`{case_id}:{origin}:{one_based_origin_ordinal_4_digits}`. The runner must bind
the complete 120-case manifest SHA-256 before executing case 1.

### 2.4 Frozen map2 Stage 0 sentinel

The sentinel is fixed before candidate data is viewed:

- source is canonical map2 at the implementation parent,
  `data/processed/maps/map2.json`;
- source SHA-256 is
  `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4`;
- canonical profile has 54 nodes, 69 directed edges, explicit storage `[52]`,
  and canonical compact-JSON SHA-256
  `3659dffdaf412739a69066b6c79dba4b83e4e3144612235f335f7c7aa5a7e323`;
- speed is fixed at `2.5 m/s`; potential-matrix compact-JSON SHA-256 is
  `c96d2095404d042558858d175db460af1faf378853a8ebdac9a92767e617e006`;
- workload source is the committed canonical 1x workload; select its first
  eight normalized rows, exactly segments `0:storage_in`, `0:storage_out`,
  `1:storage_in`, `1:storage_out`, `2:storage_in`, `2:storage_out`,
  `3:storage_in`, `3:storage_out` in that order;
- selected-row compact-JSON SHA-256 is
  `96f5d5447275fee06b8d9234b42f5b57004f0617304d08a89d19aa3a646e4803`;
- scenario is `g4irsf32_v3r2_map2_sentinel`, faults are empty, and all other
  controls use section 2.2.

The sentinel is a portability and no-mutation gate, not a performance sample.
It must complete all selected segments, pass safety, preserve off/shadow
actions/timing/calendars/events/physical state, and produce a valid census.
Zero admitted mixed-origin rows is a valid negative-control result; a row, if
present, must satisfy the same native and offline contracts as the motif.

## 3. Observation seam and pure virtual slot

Only two already-existing real external commit seams may invoke the hook:

1. `DIRECT_EXTERNAL_RESERVE`, after owner/status/edge/fault/queue/corridor and
   exact destination-calendar checks;
2. `J2_EXACT_RESERVE`, after real request/queue generations, owner/fault,
   capacity, active-grant overlap, and exact-calendar preparation checks.

The hook reads the pre-insert calendar, stack-stages one fixed numeric row, and
publishes only after the real commit succeeds. Rejection or rollback publishes
nothing and restores the census. A J2-authorized dispatch suppresses the
DIRECT hook so one physical commit cannot publish twice.

Local is the exact ordinary `choose_bag(...)` winner from L's existing source
queue at the same event epoch. Guards are: queue nonempty, bag exists,
released/live, `SourceQueue` at L, distinct from external, and L service
required. Current calendar availability is not a guard because the candidate
is a virtual slot, not a proposed commit.

For the immutable precommit calendar C, real external interval `[E0,E1)`,
local service s, and event time t:

```text
L0 = earliest_start(C,t,s)
overlap = [L0,L0+s) intersects [E0,E1) with epsilon 1e-9
L1 = earliest_start(C plus hypothetical [E0,E1),t,s)
X_insert = L1-L0
H_gap = L1-E0
```

The helper may iterate only the existing local calendar intervals. It cannot
reserve, purge, copy, or mutate the calendar. Admission requires native
external checks, all local guards, overlap, finite E0/E1/L0/L1/X/H, positive
X, and equal external/local/node service duration within `1e-9`. X never
affects an action or row admission.

The fixed row contains numeric/bool fields for observation/event/node/calendar
identity; seam/path codes; external bag, upstream, exact interval, projected
arrival, DIRECT event identity or J2 request/lineage/generations; local bag,
release/deadline/source-enqueue/choose index and guards; L0/L1/X/H/overlap;
and invariant zero action-change, future-read, global-scan, and
calendar-mutation counters. Codes are `1=DIRECT`, `2=J2`. No strings, map IDs,
route suffix, outcome, M3 comparison, or fabricated lineage appear in C++.

Census partitions every considered external commit into no-local, guard-fail,
non-overlap, staged-rollback, stored, or trace-dropped. Trace exhaustion fails
before the external commit; it is never a silent sample. The fixed row vector
is the only incremental dynamic storage. Local runtime-state bytes are zero.

## 4. Offline join and primary estimand

The native hook never reads outcomes. The ordinary payload is normalized
fail-closed:

- require final payload, full decision/event traces (shard 1/index 0), complete
  merge lifecycle, and zero dropped lifecycle rows;
- DIRECT commit identity is uniquely verified from the committed-edge decision
  with matching `arrive_event_seq`, bag/task, time, upstream and selected L,
  then matching EDGE_ENTER, EDGE_EXIT at E0, and L service completion at E1;
- J2 identity is uniquely verified from the COMMITTED/exact-slot lifecycle row
  with matching request/lineage/generations/bag/task/upstream/L/E0/E1/service,
  plus matching merge-grant EDGE_ENTER, EDGE_EXIT, and completion;
- every valid `JUNCTION_SERVICE_COMPLETE` at L yields start `complete-s`; every
  bag has exactly one L service in Stage 1;
- local joins to the first strictly later L completion for the exact local bag;
  missing, duplicate, reused, mismatched, or ambiguous identities fail the
  entire case and are never dropped or imputed.

The runner reads the namespaced
`trace_context.source_aware_destination_service_schema_id`; the generic
decision-trace `schema_id` remains unchanged.

For a joined row:

```text
Y_realized = actual_local_L_start-L0
A_gap = actual_local_L_start-actual_external_L_start
```

External actual start must equal E0 within `1e-9`. Y is signed but cannot be
negative beyond epsilon. Local wait from event time to service start is split
by union-covering actual L service intervals: covered duration is calendar
wait; the nonnegative remainder is source wait; pre-L transit/junction are
zero. Components must be disjoint and sum exactly. Bag-level cumulative waits
must not be substituted for this episode decomposition.

X/Y is the sole primary relationship. H/A is diagnostic only. Sort by
`(event_time,event_seq,observation_ordinal)` and use outcome-blind greedy bag
uniqueness; repeats remain diagnostics.

## 5. Stage 0 contract

Stage 0 uses motif `s=1,n=8,simultaneous_local_first`, both one-origin
controls, the J2 fixture, future/distant probes, and the frozen map2 sentinel.
All of the following are hard gates:

- omitted/default/explicit/repeated off canonical parity and cross-binary
  parity against a Release binary built from the implementation parent;
- selected actions, completion/timing, deterministic state/result hashes, and
  committed G31 request identity match exactly on the off path;
- repeated shadow is deterministic; off/shadow actions, completion/timing,
  calendar, ordinary events, physical state, and request identity match;
- DIRECT and J2 each produce valid unique rows; J2 cannot duplicate DIRECT;
- injected failures after staging restore row/census, calendar generation,
  event publication, and state exactly;
- future probe moves only future external/local releases from `(100,120)` to
  `(500,600)` and all rows/actions before cutoff 50 remain exact;
- distant probe adds nodes `(10,7,0,0,10,[11])`, `(11,1,1,1,10,[12])`,
  `(12,2,0,2,10,[])`, edges `(10,11,0.05,1)`, `(11,12,0.05,1)`, and task
  `(90001,release=0,deadline=10000,start=10,goal=12)`; L prefix before 50 is
  unchanged;
- no double count; local winner, L0/L1, external/local joins, wait components,
  census, trace-cap fail-closed, rollback, and bounded-memory tests pass;
- all reachable bags complete exactly once at L where applicable; zero
  calendar overlap, duplicate grant/reservation, starvation, unsafe, failed,
  conflict, unresolved deadlock, full A*, global scan, future task/route read,
  action change, or shadow calendar mutation;
- pending controllers remain within configured limits; both origins are
  served in mixed cases; controls emit zero admitted rows;
- the map2 sentinel passes its hashes, explicit-role validation, completion,
  safety, census, resource, and exact no-mutation gates.

Any failure is `NO_GO_V3R2_STAGE0_CONTRACT`; Stage 1 must not execute.

## 6. Stage 1 gates

All 120 cases execute once in off and shadow without error or truncation.
Every reachable bag completes; each bag has exactly one L service; both mixed
origins are served; pending/active grants remain bounded; safety counts are
zero; and off/shadow actions, completion times, calendars, ordinary events,
and deterministic physical state are exactly equal.

Each resource ratio must be `<=1.10`: events/completed, junction-local
accounted bytes, runtime-internal accounted bytes, and total accounted bytes
including sidecar capacity. A zero/zero ratio is exactly 1 and passes;
shadow-positive/off-zero is infinite and fails. Local, internal, sidecar, and
total bytes are reported separately.

A directional registered mixed case has at least two unique primary pairs and
at least two distinct finite X and Y values. Compute within-case Spearman rho
with average tie ranks, then equal-weight finite case rhos. GO requires:

- at least 24 directional cases and 128 unique primary bags;
- at least four mixed flows, all four services, and all three populations;
- controls have zero rows and all case/join/census values are complete;
- equal-weight mean rho > 0;
- case-block bootstrap 2.5% lower bound > 0;
- at least 60% of directional cases have rho > 0 and their two-sided Wilson
  95% lower bound > 0.5.

Bootstrap uses sorted case IDs, `random.Random(3200260827)`, 10,000 draws,
complete-case resampling, `math.fsum`, and linear percentile interpolation at
`p*(n-1)`. Wilson uses `z=1.959963984540054`. Degenerate or insufficient
evidence is NO-GO; no case, seam, flow, retry, sign, or threshold may be
selected after outcomes.

The only GO label is
`GO_V3R2_EXTERNAL_COMMIT_LOCAL_VIRTUAL_RELATION_SUPPORTED_P1_REVIEW_ALLOWED`.
Otherwise use
`NO_GO_V3R2_EXTERNAL_COMMIT_LOCAL_VIRTUAL_NOT_SUPPORTED` and do not add an
action mode.

## 7. Evidence and immutability

New outputs are:

- `outputs/tables/g4irsf32_v3r2_external_commit_local_virtual_shadow.json`;
- `outputs/reports/g4irsf32_v3r2_external_commit_local_virtual_shadow.md`.

Write atomically and never overwrite G31/V1/V2 evidence. Bind audit base,
protocol bytes/hash, clean implementation commit, source and loaded binary
hashes, full manifest/profile/potential/request hashes, case rows, ordinary
trace and primary-row hashes, all raw gates, and issue/remediation ledger.

All 120 cases, controls, weak/strong/agreeing/disagreeing rows stay in the
denominator. Join failure fails the case. The fixed population, map2 sentinel,
formulas, ordering, hashes, gates, seed, draws, resource limit, and signs cannot
change after candidate evidence is viewed. A negative gate may cause one
minimal attributable V3R3 protocol, but it may not relax a threshold, delete a
NO-GO, select outcomes, or retain superseded production complexity.
