# G4IRSF32 V3R12 arrival-covered Nanning P0 addendum

Protocol identity:
`G4IRSF32_V3R12_ARRIVAL_COVERED_NANNING_P0_ADDENDUM_20260829`.

Frozen on 2026-08-29 (Asia/Shanghai), after the terminal V3R11 Nanning
non-overlap result and before any formal V3R12 control, shadow, or P1 action
execution.  V3R12 does not create a new synthetic population: it reuses and
fully deep-replays the immutable V3R11 Stage 0/1 PASS artifact against the
same already-bound G32 binary.

## 1. What V3R11 established and why it stopped

V3R11 formally passed synthetic Stage 0 and Stage 1, including the original
120 safety cases and the 24 identification cases.  Its Nanning 1x and 2x
shadow runs passed every exact-off, completion, safety, resource, service, and
telemetry-conservation gate, but each produced one `non_overlap` opportunity
and no stored observation.

The selected local services ended about 59 seconds before the selected
external work reached node 49.  The V3R7 selector had aligned local work with
the external `53->49` commit and had not included the frozen 60.1-second edge
travel when predicting the destination-service slot.  V3R11 therefore remains
a terminal NO-GO and its artifacts are not overwritten or reclassified.

## 2. Smallest geometry that the existing shadow can actually observe

The shadow seam is the external `53->49 EDGE_ENTER` commit.  It may inspect
only local work already released at that epoch.  The first external
destination reservation begins 60.1 seconds after the first commit, while
node-49 service lasts 1.0 second.  Therefore a local bag can remain in the
source queue at a later external commit only when prior external reservations
cover the otherwise available interval up to that later external slot.

With one-second external slot spacing, the first possible observable commit
has zero-based rank 60:

- first commit: `e + 0.001`;
- first external arrival: `e + 0.001 + 60.1`;
- observable commit: `e + 0.001 + 60`;
- current external slot: `e + 0.001 + 60 + 60.1`.

This requires at least 61 external rows.  A mixed-origin observation also
requires at least one local row.  The 62-row cohort below therefore reaches
the cardinality lower bound; no smaller cohort can realize this seam without
reading a future release or changing the runtime.

## 3. Frozen engineering canary

For both 1x and 2x regenerated workloads:

1. retain external rows with `start=53`, `leg=storage_out`, and
   `pass_time=68400.0`;
2. order them by `(pass_time, segment_id, task_id)` and take the first 61;
3. set `first_arrival=68460.101` and `rank60_commit=68460.001`;
4. from all `start=49` rows in the open interval
   `(first_arrival-1.0, rank60_commit)`, take the canonical first row;
5. the selected local identity must be `25195:direct`, task `25195`, released
   at `68459.64183`;
6. add only `source=external|local`, then canonically order the 62 rows.

The ordered segment/task identity vector is the same in 1x and 2x.  Other
regeneration metadata such as source-line numbering is allowed to retain its
scale-specific canonical value and is validated by the existing workload
contract.

The rank-60 external identity is `23076:storage_out`; its commit is
`68460.001`, while its projected node-49 service slot begins at `68520.101`.
The local bag was released 0.35917 seconds before that commit and cannot fit
in the 0.45917-second gap before the first external arrival.

## 4. Disclosure: this is not an outcome-blind performance cohort

This exact release was chosen after bounded diagnostic replay of the frozen
input exposed two facts: the correct 61+1 arrival-covered geometry, and the
pre-existing zero-tolerance stale-arbitration gate triggered by several other
large bursts.  The selected canary was then observed to satisfy the unchanged
G31 safety gate and to expose the intended G32 state.

Consequently V3R12 must record:

- `selection_outcome_blind=false`;
- `selection_role=ENGINEERING_EXISTENCE_CANARY_NOT_EFFECT_ESTIMATE`;
- the diagnostic origin of the fixed cohort;
- no claim about event frequency, prevalence, effect size, or closed-loop
  performance from this canary.

The formal V3R12 run is a clean-build reproducibility confirmation, not a
second independent discovery sample.  Directional support remains supplied
by the separately fixed 24-case synthetic identification cohort.  Stage 2
real-map cases must still be registered from control traces before any
closed-loop candidate outcome, exactly as required by the original action
plan.

## 5. Diagnostic evidence that justified freezing, not formal evidence

Read-only temporary probes, with no tracked output publication, produced the
following engineering checks for both scales:

- 62 requested and 62 completed;
- zero failed, final-active, conflict, deadlock, full-A*, global-scan, event
  limit, and time-limit findings;
- zero `merge_grant_stale_arbitration_count` and zero
  `stale_arbitration_event_count`;
- one uniquely reconstructable G31 `53->49` event with a released local
  source winner;
- one G32 stored observation, zero `non_overlap`, local ready count one, and
  `L0` exactly equal to the external slot start.

These probes only established that a formal run is worth performing.  They
do not occupy the registered V3R12 output paths and cannot authorize P1.

## 6. Unchanged hard gates and implementation boundary

V3R12 changes no C++ runtime, action, mode semantics, map, workload row,
service value, threshold, or closed-loop policy.  The following remain hard
requirements:

- G31 omitted/default-off control passes at both scales;
- stale arbitration, conflict, failure, unsafe action, global scan, future
  route, and full A* remain exactly zero;
- every selected bag completes and receives exactly one node-49 service;
- the G32 shadow changes no ordinary request, action, event, timing, or
  calendar state;
- `future_release_read_count`, `global_scan_count`, action changes, and
  calendar mutations remain zero;
- both scales contain at least one admitted node-49/upstream-53 observation;
- the immutable clean-build V3R11 Stage 0 and complete 120+24 Stage 1 PASS
  population deep-replays in full, with the same bound G32 binary; V3R12 does
  not rerun those identical 144 cases because neither runtime nor population
  changed;
- map2 exact-off and sentinel gates remain unchanged.

Historical V3R7 control identity remains permanently bound to historical
V3R11 synthetic evidence.  V3R12 uses a separate active control revision; it
must not mechanically reinterpret the V3R7 artifact.

## 7. Registered output paths and execution order

- control:
  `outputs/tables/g4irsf32_v3r12_nanning_p0_control_selection.json`;
- reused prerequisite:
  `outputs/tables/g4irsf32_v3r11_synthetic_stage01.json` (read-only, full deep
  replay; no V3R12 synthetic output is created);
- final campaign:
  `outputs/tables/g4irsf32_v3r12_p0_campaign.json`;
- report:
  `outputs/reports/g4irsf32_v3r12_p0_campaign.md`.

Execution order is active G31 control, full deep replay of the immutable V3R11
Stage 0/1 artifact, Nanning G32 shadow, then composition.  This removes an
identical 144-case rerun without weakening any gate.  Any failed gate produces
an append-only NO-GO and stops; P1 remains absent until the composed V3R12
result passes every gate.
