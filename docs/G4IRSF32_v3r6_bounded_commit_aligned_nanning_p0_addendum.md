# G4IRSF32 V3R6 bounded commit-aligned Nanning P0 addendum

Protocol identity:
`G4IRSF32_V3R6_BOUNDED_COMMIT_ALIGNED_NANNING_P0_ADDENDUM_20260828`.

Frozen on 2026-08-28 (Asia/Shanghai), after the formal G31-only V3R5
control and before any formal G32 Nanning run, synthetic Stage 0/1 run, or
P1 action implementation/outcome. This revision is G31-control-informed but
remains G32-outcome-blind.

## 1. Preserved negative history

Neither earlier revision is retroactively declared GO.

- V3R3 terminal artifact:
  `outputs/tables/g4irsf32_v3r3_nanning_p0_control_selection_attempt4_no_event.json`;
  file SHA-256
  `cc9c7ed4a19e2db3bcfa4397324de2ccecfd08fee862a95cb250d234c67074cd`;
  zero qualifying events at both scales and `g32_executed=false`.
- V3R5 terminal artifact:
  `outputs/tables/g4irsf32_v3r5_nanning_p0_control_selection_attempt1_audit_failed.json`;
  322,188,323 bytes; file SHA-256
  `bcde3e4a68609432ce74b6996ff8798928770846984e181fa7ad2d6f3497f56c`;
  strict content SHA-256
  `1f4d2bbcf98eaf74c962fc0cbdd11cd53a7ba6cf6120cb44119c7698293dc94a`;
  `g32_executed=false`.

V3R5 established the target state: 1x and 2x produced respectively 14 and
19 real external `53->49 EDGE_ENTER` events with a released live local
node-49 winner. All 319/494 selected bags completed, with zero failed or
active bags, no time/event/trace limit, no global service overlap, and exact
population identity. It nevertheless remains NO-GO because the full modal
bursts produced 41/155 `merge_grant_stale_arbitration_count` events, which is
an existing frozen safety hard gate. The 2x lifecycle audit also exposed one
telemetry-order false negative caused by an approximately 3.64e-12-second floating-point
representation difference; fixing that audit cannot turn V3R5 into GO because
the independent stale-arbitration hard gate remains failed.

## 2. Single attributed revision

V3R6 changes only the size of the already frozen modal external burst. The
V3R5 rule selected every one of the 310/470 external rows released at `t*`.
That simultaneous population was much larger than the earlier audited
control scale and introduced avoidable controller churn unrelated
to proving that the mixed-origin state exists.

An independent pre-execution review rejected an initial 32-row prefix design
without running it: the V3R5 G31 control trace placed the first qualifying 1x
external row at canonical rank 60 (the 14 qualifying rows occupied ranks
60--73). A 32-row prefix would therefore remove the already demonstrated 1x
state. V3R6 uses 64, the smallest power-of-two canonical prefix containing
that first control-trace rank. It does not select any qualifying row by
identity and does not search multiple caps.

For each scale independently, V3R6:

1. regenerates and validates the same frozen G31 Nanning workload and pools;
2. computes the same modal external release `t*`, with the same earlier-time
   tie break;
3. canonically orders all external rows at `t*` by
   `(pass_time, segment_id, task_id)` and selects the first 64;
4. retains every local node-49 source row in the unchanged half-open window
   `[t*, t* + 120.0 seconds)`;
5. adds only `source=external|local` and canonically orders the combined rows
   by `(pass_time, segment_id, task_id)`.

The constant 64 was fixed before any V3R6 execution. The control-trace rank is
permitted G31 preregistration evidence; the cap is not searched over and is
not a performance threshold. No G32 or candidate-outcome data exists, and no
row identity is chosen from a completion, wait, event, service, or safety
outcome.

Selector identity:
`MODAL_EXTERNAL_RELEASE_CANONICAL_FIRST_64_PLUS_120S_LOCAL_WINDOW_V1`.

## 3. Frozen selection identities

| Scale | `t*` | External | Local | Total | external release histogram SHA-256 | original rows SHA-256 | projected rows SHA-256 | projection identity SHA-256 | selected segment IDs SHA-256 |
|---|---:|---:|---:|---:|---|---|---|---|---|
| 1x | 23700.0 | 64 | 9 | 73 | `29b791b11683997127cab95c7ea9762c2b93150b38328bb30df08527630381dd` | `24c9bb53808276fc0abef8e5dff26b72d63b475e160609c2dd66c9c07a1507c7` | `4962227eb0411ce213dd314158366520a26fe830889eb9af38904e5bebd0e1de` | `05401290bc88608e92d245cdcf417fc9680fb3d9590021bee6d0e6f909fbcf4c` | `3b1b9b6c25344844e2814b01143576e5801f4b7c86afde7dac1033e69d482c5b` |
| 2x | 22200.0 | 64 | 24 | 88 | `ba35a35236263aa430ea8290af271934546e99d9f06605fe7b99784596d7a534` | `7bd8783eb5b1fafefdaecb1847a728e81e03371e99c6f66ed62db106f24edfa0` | `777c6a86f0a867ddf84df087ea9672351278a5ead25480dd899b5cc18b1b50cc` | `4ec88092efa345345594b8763931d22c82fe7d7ef991598019d2a9e7a5ecd1b3` | `81f98cf9177b38e119ffd44f55d755c6a0c99c5e28c5c818219ec067ae7dbb4a` |

The full modal-release histogram remains an identity input even though the
external output is bounded. Counts and hashes are identity gates, not GO
thresholds.

## 4. Unchanged G31 control gate

The formal V3R6 control still runs both scales with the exact frozen G31
Release binary in omitted/default-off mode. Every V3R5 gate remains in force:

- exact selected population, request, profile, potential, binary path/SHA,
  sources and dependencies from start to end;
- every requested bag completes once with zero failed/active/late bags and no
  event, time, or trace limit;
- zero safety, conflict, stale-arbitration, full A*, global scan, future-route,
  service-overlap, duplicate reservation/grant, permanent-starvation, or final
  pending-state violation;
- at least one real external `53->49 EDGE_ENTER` with exactly one released,
  live local node-49 source winner and uniquely reconstructable service
  episodes.

The qualifying-event threshold remains at least one per scale. No V3R5
observation becomes a threshold. A negative result is archived append-only and
cannot be overwritten or reclassified.

## 5. Narrow lifecycle telemetry correction

Lifecycle semantics remain exactly
`REQUESTED -> ISSUED -> PREPARED -> COMMITTED -> terminal`. The offline audit
may canonicalize those states only when raw telemetry timestamps differ by no
more than the existing `1e-9` audit epsilon. Missing/duplicate states, grant
identity drift, a real reversal larger than epsilon, invalid terminal state,
count mismatch, or pending final state remains fail-closed. This corrects
serialization order only; it changes no runtime event, grant, state, or safety
threshold.

## 6. Promotion order remains closed

Only a formal V3R6 G31 control PASS permits the unchanged synthetic Stage 0
and fixed 120 Stage 1 cases. Only their GO permits the exact V3R6 Nanning rows
to run once with the final clean G32 binary in shadow mode. Only a two-scale
shadow GO may authorize a separately frozen P1 action implementation/review.

V3R6 therefore removes neither a negative result nor a hard gate. It bounds
one evidence cohort and corrects one sub-epsilon audit ordering defect; no
runtime algorithm, map, workload row, threshold, action, service value, or
closed-loop policy changes.
