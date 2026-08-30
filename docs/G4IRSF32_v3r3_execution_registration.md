# G4IRSF32 V3R3 execution registration

Registration ID:
`G4IRSF32_V3R3_EXECUTION_REGISTRATION_20260827`.

Frozen `2026-08-27` (Asia/Shanghai), before any formal V3R3 synthetic,
Nanning-control, or Nanning-G32 run. Status:
`FROZEN_EXECUTION_REGISTRATION_NO_DATA`.

This registration resolves execution details left implicit by
`G4IRSF32_v3r3_measurement_semantics_protocol.md`. It changes no population,
threshold, selection rank, algorithm, or gate.

## 1. Nanning source projection

The regenerated G31 canonical rows do not use the literal source labels
`external|local`. Selection retains each complete original canonical row and
adds an explicit, deterministic origin projection:

- an E-pool row (`start=53`, segment suffix `:storage_out`) is executed with
  request `source="external"`;
- an L-pool row (`start=49`) is executed with request `source="local"`.

No other row is selected. The control-selection artifact binds both the
complete original selected rows and the projected request rows, their two
canonical hashes, and an exact one-to-one identity map. The projection may not
change task ID, segment ID, release, deadline, start, or goal. Node 53 remains
the storage source by the explicit role list, independent of its display
source label.

Nanning origin-completion and service-sequence conservation use these projected
`external|local` labels. They do not compare against the synthetic case's
counts or invent a third origin.

## 2. Complete Nanning request projection

For each scale the scenario is
`g4irsf32_v3r3_nanning_p0_{scale}x`. G31 control and G32 shadow use the same
scenario and same ordinary request. G31 omits the G32 tail; G32 changes only
`source_aware_destination_service_mode=shadow` and its trace limit.

The request uses the complete V3R2 section 2.2 projection, including:

```text
queue_discipline=fifo
retry_interval=0.25
minimum_service_seconds=0.001
dispatch_headway_seconds=0.001
history_limit=8
max_decisions_per_bag=512
max_events=2000000
max_simulation_time=-1
trace_limit=200000
event_trace_limit=200000
summary_only=false
trace_shard_count=1; trace_shard_index=0
local_queue_capacity=0
deadlock_retry_threshold=8
enable_source_admission=false
enable_backpressure=false
enable_pibt_lite=false
enable_deadlock_escape=true
enable_fault_policy=true
fault_windows=[]
resource_semantics=R3_java_node_window_compatible
pressure_mode=off; admission_mode=off
pibt_mode=P2; pibt_max_depth=2; pibt_max_ready_bags=8
priority_mode=Q0; pibt_preference_mode=current
scorer_mode=S4_queue_aware_rule_only
framework_mode=event_loop_one_step
event_semantics=E4_batch_plus_destination_merge_request
merge_grant_rule=M3
merge_grant_timing_mode=jit_fair_aging_deadline
g4irsf20_event_hotpath_policy=E2
g4irsf16_supervisor_mode=off
enable_opportunity_telemetry=false
enable_s4_local_potential_descent_guard=true
enable_s4_direct_neighbor_merge_calendar_visibility=true
complete_on_goal_arrival=true
storage_source_nodes=[53]
```

All remaining numeric fields are exactly those in V3R2 section 2.2. The full
ordered request key set and canonical request hash are evidence; an omitted,
extra, legacy, model, DLP, learned, or map-ID policy field fails closed. The
profile is the complete frozen Nanning profile and its deterministic
service-aware potential is recomputed at 2.5 m/s.

## 3. Ordered legacy diagnostic

For every synthetic or Nanning case, the ordered legacy-wait vector is sorted
by integer `runtime_bag_id`. Runtime IDs must be the exact contiguous request
order `0..N-1`. Each vector element binds:

```text
(runtime_bag_id, segment_id, task_id, source,
 finite_total_local_wait, native_starved,
 independently_recomputed_wait_over_120)
```

Per-origin counts and maxima are computed from the same ordered vector. This
order is used for its canonical hash in off and shadow.

## 4. Exact bounded-memory Nanning pair selection

Expected pool cardinalities before selection are frozen as:

| scale | E pool | L pool | mathematical pair count |
|---:|---:|---:|---:|
| 1x | 15,097 | 2,807 | 42,377,279 |
| 2x | 30,194 | 5,614 | 169,509,116 |

The mathematical rank remains the exact rank in the V3R3 protocol. An
implementation must not materialize the Cartesian product. It may use sorted
local releases, binary search, per-external lazy nearest-neighbour streams, and
a global heap, provided that emitted pairs are identical to a full sort by the
frozen four-part key.

Before executing the real pools, focused tests must compare the optimized
selector byte-for-byte with a brute-force Cartesian oracle on fixed small
pools covering:

- equal absolute distance on both sides of projected arrival;
- equal release and `max(releases)` ties;
- external and local segment-ID tie breakers;
- reuse conflicts that require advancing both external and local candidates;
- fewer than 32 feasible pairs and duplicate identity rejection.

The artifact records full E/L pool cardinalities and canonical hashes, the 32
selected rank keys, original/projected 64-row hashes, and selector algorithm
ID `EXACT_LAZY_GLOBAL_RANK_EQUIVALENT_TO_CARTESIAN_V1`. Any oracle mismatch,
pool-count/hash mismatch, duplicate row, or fewer than 32 disjoint pairs fails
before a native run.

## 5. Artifact paths and ordering

The G31 control-selection artifact is:

`outputs/tables/g4irsf32_v3r3_nanning_p0_control_selection.json`.

It is written atomically with strict JSON (`allow_nan=false`) and never
overwrites a G31 or V3R2 artifact. The later G32 shadow evidence is stored under
the V3R3 campaign output and binds this exact control-selection file and hash.

The sequence is mandatory:

1. freeze this registration;
2. test selector/oracle and evidence validation;
3. execute and freeze G31 control selection for both scales;
4. freeze the G32 implementation/binary identity;
5. run synthetic Stage 0 and all 120 cases;
6. only after their GO, run the exact Nanning shadow rows;
7. only after the Nanning shadow GO may a separate P1 action protocol be
   designed.

