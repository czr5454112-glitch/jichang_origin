# G4IRSF32 V3R5 commit-aligned Nanning P0 addendum

Protocol identity:
`G4IRSF32_V3R5_COMMIT_ALIGNED_NANNING_P0_ADDENDUM_20260827`.

Frozen on 2026-08-27 (Asia/Shanghai), after the G31-only V3R3 control
attempts and before any formal G32 Nanning run, synthetic Stage 0/1 run, or
P1 action implementation/outcome. This addendum is control-informed but
G32-outcome-blind.

## 1. Preserved terminal V3R3 result

V3R3 is not retroactively declared GO. Its exact frozen 32-pair-per-scale
cohort remains a terminal negative:

- artifact:
  `outputs/tables/g4irsf32_v3r3_nanning_p0_control_selection_attempt4_no_event.json`;
- file SHA-256:
  `cc9c7ed4a19e2db3bcfa4397324de2ccecfd08fee862a95cb250d234c67074cd`;
- strict content SHA-256:
  `73b66386a62f374268d593f079fa440ec266d28fb2c4cffabfe1294991396d6a`;
- status:
  `NO_GO_NANNING_P0_CONTROL_SELECTION_NO_EVENT` at both 1x and 2x;
- G32 execution: `false`.

The V3R3 pairing aligned a local release to the external projected arrival
about 60 seconds after the external commit observation seam. At every selected
external `53->49 EDGE_ENTER`, the current node-49 source queue was empty. No
pair, release, rank, threshold, or recorded V3R3 verdict may be altered.

## 2. Why a new revision is allowed

The original action plan requires a Nanning small shadow slice to establish
that the mixed-origin state exists before it is connected to the existing J2
authority. It also explicitly allows real-map cases to be selected from a G31
control trace before any candidate outcome is observed.

V3R5 therefore changes only the G31 cohort-selection seam. It does not change
the P0 helper, row schema, Stage 0 fixtures, fixed 120 Stage 1 cases, service
values, populations, flows, bootstrap seed/draws, gates, resource limit,
runtime action, map, workload rows, or G31/G32 binaries. The revised selector
uses only committed workload identity and release fields. Exploratory G31-only
execution confirmed feasibility before this freeze; no G32 Nanning or P1
outcome was available.

## 3. Frozen commit-aligned selector

For each scale independently:

1. Regenerate and validate the exact committed G31 Nanning workload and the
   same frozen external/local pools as V3R3.
2. In the external pool (`start=53`, `leg=storage_out`), count rows by exact
   `pass_time`.
3. Let `t*` be the release time with maximum external multiplicity; break an
   exact multiplicity tie by the earlier release time.
4. Select every external row whose release is exactly `t*`.
5. Select every local node-49 source row with release in the half-open window
   `[t*, t* + 120.0 seconds)`.
6. Add only the evidence label `source=external|local`; preserve every other
   field byte-for-value.
7. Canonically order the selected rows by
   `(pass_time, segment_id, task_id)`.

Selector identity:
`MODAL_EXTERNAL_RELEASE_PLUS_120S_LOCAL_WINDOW_V1`.

The selector reads no completion, wait, queue, event, service, safety, G32,
or candidate-outcome field. It does not enumerate an external-by-local
Cartesian product and adds no runtime policy.

## 4. Frozen selection identities

| Scale | `t*` | External | Local | Total | external release histogram SHA-256 | original rows SHA-256 | projected rows SHA-256 | projection identity SHA-256 |
|---|---:|---:|---:|---:|---|---|---|---|
| 1x | 23700.0 | 310 | 9 | 319 | `29b791b11683997127cab95c7ea9762c2b93150b38328bb30df08527630381dd` | `3789ecb6a7c0248c66fea7bb73274bffcd1e811a0a8c61bd50aa0b4ae058e805` | `0e26f27c905f104e54c6434354a790c912143bb7865522542cb2d54576e710d6` | `c6e3394ac91a2a2d2922750e97ffda04559496e1c3c1257fe1f134fe1e559158` |
| 2x | 22200.0 | 470 | 24 | 494 | `ba35a35236263aa430ea8290af271934546e99d9f06605fe7b99784596d7a534` | `de9fae82493fa8c61fbf7d8de1dafa03d6a9d3a205cc5e0bf061f42e52bd2c74` | `300ef791e76f3b1af7ed70cbce48fcaa8e4677e94b1918a0dfd5ffa6d28fe51d` | `e0325fd8910a942f67f1587ff607cfd96ca0a9b8774fbfb54fdcc19648467b28` |

The exact counts and hashes are identity gates, not performance thresholds.

## 5. G31 control gate

Run the selected 1x and 2x requests with the same frozen G31 Release binary in
omitted/default-off mode. For each scale, require:

- exact selected population identity and complete ordinary trace;
- all requested bags complete once, with zero failed/active/late bags and no
  event/time limit;
- no service-calendar overlap, duplicate reservation/grant, permanent
  starvation, final queue/incoming state, safety, full A*, global scan, or
  future-route violation;
- at least one real external `53->49 EDGE_ENTER` at which the ordinary source
  queue contains exactly one released live local node-49 bag, with both service
  episodes uniquely reconstructable and non-overlapping;
- frozen sources, execution dependencies, request, profile, potential, binary
  path/SHA, selection rule, counts, and hashes unchanged from start to end.

Zero qualifying events remains
`NO_GO_V3R5_NANNING_P0_CONTROL_SELECTION_NO_EVENT`; any other failed gate
remains a separate audit NO-GO. G32 must not execute after either result.

## 6. Unchanged promotion order

Only a V3R5 G31 control PASS permits the unchanged formal synthetic Stage 0
and all fixed 120 Stage 1 cases. Only their GO permits the exact same selected
Nanning requests to run once with the final clean G32 binary in `shadow` mode.
Only a two-scale Nanning shadow GO may authorize a separately frozen P1 action
implementation/review.

Thus V3R5 preserves the stricter P0 ordering while correcting the observation
alignment. It does not waive a negative gate, turn V3R3 into GO, or move any
Stage 2/3/4 performance threshold.
