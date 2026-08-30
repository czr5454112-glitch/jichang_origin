# G4IRSF32 V3R4 P0 telemetry-completeness addendum

Status: `FROZEN_BEFORE_FORMAL_G31_CONTROL_OR_G32_OUTCOME_EXECUTION`

This addendum closes literal P0.3/P0.5 evidence fields from the original
`G4IRSF32_cross_map_next_stage_action_plan.md`. It is evidence-only. It does
not change the V3R3 population, thresholds, outcome-blind Nanning selection,
runtime action, route guard, queue capacity, PIBT, destination authority, or
Stage 0/1 ordering.

## 1. Namespaced row revision

The exact namespaced row schema is:

`czr005.g4irsf32.external_commit_local_virtual_slot_shadow.v3r4`

It preserves every V3R2 row field and adds the following commit-preflight
snapshot fields:

| Field | Frozen meaning |
|---|---|
| `local_source_ready_count` | Current destination node `source_queue.size()`; all entries are already released and have no destination-service reservation. |
| `local_source_uncovered_service_work_seconds` | `local_source_ready_count * local_service_seconds`; no task scan or calendar mutation. |
| `external_scheduled_incoming_count` | Existing current-node `JunctionState.scheduled_incoming` scalar. |
| `destination_pending_count` | Existing current-node bounded destination-merge controller `pending_count()`, or zero if no controller exists. |
| `oldest_local_wait_age_seconds` | `max(0,event_time-source_enqueued_at)` for the front of the existing source queue. |
| `oldest_external_wait_age_seconds` | Existing current-node bounded destination controller `oldest_pending_age(event_time)`, or zero when no pending request exists. |
| `service_calendar_next_free_seconds` | Exact alias of `L0`, the current immutable calendar's earliest local start. |
| `existing_calendar_wait_seconds` | Exact nonnegative alias `L0-event_time`; delay already present before the hypothetical external interval. |
| `selected_action_from_node` | Upstream endpoint of the real external commit being observed. |
| `selected_action_to_node` | Current destination service node of that commit. |
| `selected_action_kind_code` | Same frozen seam code as the real action: `1=DIRECT`, `2=J2`. |
| `local_origin_code` | Frozen code `1=local`. |
| `external_origin_code` | Frozen code `2=external`. |

`calendar_generation_before` remains the required generation field.
`action_changed`, future-read, global-scan, and calendar-mutation counters
remain exact zero. Actual subsequent source, junction, calendar, transit, and
total waits remain in the already frozen offline outcome join; they are not
read by the native hook and are not duplicated into its pre-outcome row.

All added values are fixed numeric POD members in the existing bounded row.
They read only the current node's source queue, service calendar, scheduled
incoming scalar, and bounded destination controller. They introduce no cache,
policy, arbiter, event, map/node special case, model, route suffix, future task
read, or global bag/task scan. The row vector remains the only incremental
dynamic storage.

## 2. Exact validation

Formal evidence must reject the whole case unless:

- the row key set exactly matches V3R4;
- counts and ages are finite/nonnegative and the local ready count is positive;
- uncovered work equals ready count times node service within `1e-9`;
- a zero pending count has zero oldest-external age;
- next-free equals `L0` within `1e-9`;
- existing calendar wait equals `L0-event_time` within `1e-9`;
- selected-action endpoints and kind equal the real commit identity;
- origin codes are exactly `1` and `2`;
- ordinary `LOCAL_QUEUE_UPDATE` replay independently reproduces local ready
  count, uncovered work, chosen index, winner, enqueue time, and oldest age.

The calendar estimator must also satisfy `L0,L1 >= event_time-1e-9`, the
hypothetical local interval must not overlap the inserted external interval
(`L1 >= E1-1e-9`), and `H_gap >= -1e-9`.

## 3. Original motif wording

The frozen motif already retains downstream node 2 with explicit node type 4
(diverter) followed by goal node 3. “Retain a diverter node and a goal” is a
role/path-integrity requirement here; it is not evidence for a second route or
an alternate-path performance claim. No topology change is introduced by this
addendum.

## 4. Promotion boundary

Synthetic Stage 0/1 remains insufficient to authorize P1. The only eligible
final P0 result must still bind the registered G31 control artifact, clean G32
binary/source identity, immutable synthetic artifact, and both Nanning shadow
scales. Injectable test runners or loaders have no `FINAL_GO` authority.
