# G4IRSF32 V3R7 minimal pre-arrival overlap Nanning P0 addendum

Protocol identity:
`G4IRSF32_V3R7_MINIMAL_PREARRIVAL_OVERLAP_NANNING_P0_ADDENDUM_20260828`.

Frozen on 2026-08-28 (Asia/Shanghai), after the formal G31-only V3R6
control and before any V3R7 executor, G32 Nanning run, synthetic Stage 0/1
run, or P1 action implementation/outcome. This revision is informed by
append-only G31 control evidence and frozen workload geometry, but remains
G32-outcome-blind.

## 1. Preserved negative history

No earlier revision is retroactively declared GO.

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
  14/19 qualifying events, 41/155 stale arbitrations, and
  `g32_executed=false`.
- V3R6 terminal artifact:
  `outputs/tables/g4irsf32_v3r6_nanning_p0_control_selection_attempt1_audit_failed.json`;
  63,256,026 bytes; file SHA-256
  `d025204c0be56b79e1cf728d68b4051d444277c71b05fae68fcadc106e74dfc3`;
  strict content SHA-256
  `e7febfee7120b60e6daaf1b4262a4a44816691f8f477379c823a2d567ea82db6`;
  4/2 qualifying events, 11/21 stale arbitrations, and
  `g32_executed=false`.

V3R6 completed all 73/88 bags, with zero failed or active bags, no limit,
conflict, global scan, full A*, pending-state, global-service, permanent
starvation, or lifecycle failure. Its two false top-level checks are both
caused by the same nonzero frozen stale-arbitration safety field. V3R6
therefore remains terminal NO-GO and its PASS path remains absent.

## 2. Problem and single attributed handling

V3R5 and V3R6 proved that the required mixed-origin state is real, but both
used a large simultaneous external burst to create it. That burst also
created superseded destination-merge wakeups. The old lazy wakeup later
failed its generation/time match and incremented
`merge_grant_stale_arbitration_count`, which is an existing zero-tolerance
safety hard gate and cannot be relaxed.

V3R7 does not try another arbitrary prefix cap. It uses the already frozen
release times and service geometry to select the smallest cohort that places
one external `53->49` commit strictly inside a local-local node-49 service
overlap. The queue is therefore caused directly by two local releases, not by
a long external burst.

Frozen control geometry:

- external first-entry offset: `0.001` seconds;
- node-49 service duration and external entry stride: `1.0` second;
- source retry interval: `0.25` seconds;
- exact 53-to-49 travel at 2.5 m/s: `60.1` seconds;
- audit epsilon: `1e-9` second.

For each scale independently, V3R7:

1. regenerates and validates the complete frozen G31 Nanning workload and
   exact external/local pools;
2. canonically orders external bursts and local node-49 rows by
   `(pass_time, segment_id, task_id)`;
3. considers only adjacent local rows `A,B` whose release gap is strictly
   inside `(EPSILON, 1.0-EPSILON)`;
4. for every external release `e`, computes
   `rank=max(0, ceil((B.release-e-0.001)/1.0))` and
   `commit=e+0.001+rank*1.0`;
5. retains a candidate only when that rank exists, both consecutive local
   services can finish before the first external arrival using the exact
   frozen retry calendar
   (`max(B.release+0.25,A.release+1.0)+1.0 <=
   e+0.001+60.1-EPSILON`), and
   `B.release+EPSILON < commit < A.release+1.0-EPSILON`;
6. chooses the minimum canonical tuple
   `(rank+1, e, A.release, B.release, A identity, B identity)`;
7. selects exactly the canonical external prefix through that rank and the
   two local rows, adds only `source=external|local`, and canonically orders
   the combined rows.

A local pair may release before `e`: the frozen gate requires the local
winner to be released and live at external commit, not after external
release. Excluding that valid case would retain an unnecessary extra external
row in 2x. No completion, wait, event, queue, service outcome, qualifying
identity, lifecycle, safety, or G32 field is read by the selector.

Selector identity:
`MINIMUM_EXTERNAL_PREFIX_ADJACENT_LOCAL_SERVICE_OVERLAP_V1`.

## 3. Frozen selection identities

| Scale | external release | burst multiplicity | prefix / local / total | zero-based `commit_rank` | predicted commit | local releases | candidate count | candidate-set SHA-256 |
|---|---:|---:|---:|---:|---:|---|---:|---|
| 1x | 58200.0 | 117 | 4 / 2 / 6 | 3 | 58203.001 | 58202.30181, 58202.90035 | 9 | `0a62a1c72182b832f04ae0835bc6b71ef32ec1ae81e40d76afde80835cbf1684` |
| 2x | 45000.0 | 127 | 1 / 2 / 3 | 0 | 45000.001 | 44999.16006, 44999.31313 | 82 | `f4e8b6232bd9ed8bfed92d3f279232a57643b3f8e7d7dc5901b35522c357d54e` |

| Scale | ordered selected segment IDs | original rows SHA-256 | projected rows SHA-256 | projection identity SHA-256 | selected IDs SHA-256 |
|---|---|---|---|---|---|
| 1x | `16044:storage_out`, `16090:storage_out`, `16125:storage_out`, `16575:storage_out`, `20434:direct`, `20435:storage_in` | `79d321de396cbbaffa786c11d8a032d57ad0be448b021f680e0f890dc7a94478` | `48727b540fe2853b392e3cc10ee5a0995c735e4154dd5e9a5d6c224028a3dbd3` | `691d6015af2eae895351afeca33732cd4c4a01fc5293cab90d367707ccfa0874` | `fe20379a1c66ed627654c51e66ce4e3e11974b845196e207e2d3d18dc328dda6` |
| 2x | `15198:storage_in`, `43305:storage_in`, `10529:storage_out` | `5b2c8d6b80159f29abdf38e42c8cf7a3f514836c927479a6e16f6890b7924f8f` | `7b86b3fc69bd6a9d9984f1f48a9e64f5e513c08bd416b9a93c00f6d27c89b1bd` | `eddb032a9b584dfb9b5b249272f586efd6f15aa82a7a1baad8deb49a532657b0` | `bdf084982830882a1b36ac6e67d2f198a0fb13ba33ab0f1a0691ca9f1484219d` |

The complete external release histograms remain frozen at
`29b791b11683997127cab95c7ea9762c2b93150b38328bb30df08527630381dd`
for 1x and
`ba35a35236263aa430ea8290af271934546e99d9f06605fe7b99784596d7a534`
for 2x. The omitted/default-off 65-key G31 request SHA-256 values are
`395cbb2a4bd77c1e25adefc3815c23954019adfe73bf259adfed0c87eaee7ade`
and
`f586307fd8c1ff130f240b6d56a9999824a831868de63b7ce896360a7f39069c`.
Counts and hashes are identity gates, not performance thresholds.

## 4. Causal prediction is not a verdict

For 1x, local A occupies node 49 over approximately
`[58202.30181,58203.30181)`; local B releases at `58202.90035`; the fourth
external commit is predicted at `58203.001`. For 2x, A occupies approximately
`[44999.16006,45000.16006)`; B releases at `44999.31313`; the first external
commit is predicted at `45000.001`. In both cases B is the only selected local
row waiting at the predicted commit, and both local services precede the first
external arrival by roughly sixty seconds.

The frozen timing margins are far above epsilon: commit follows B release by
`0.10065/0.68787` seconds, precedes A completion by `0.30081/0.15906`
seconds, and both local services can clear before the first external arrival
with `55.79919/58.94094` seconds remaining for 1x/2x respectively.

This is preregistered causal geometry, not a recorded runtime PASS and not a
promise that stale will be zero. Only one formal G31 execution after a clean
commit may establish the outcome. A negative result must be archived
append-only before another revision is designed.

## 5. Unchanged G31 control gate

The formal V3R7 control runs both scales with the exact frozen G31 Release
binary in omitted/default-off mode. Every prior hard gate remains in force:

- exact selected population, request, profile, potential, binary path/SHA,
  sources and dependencies from start to end;
- every requested bag completes once with zero failed/active/late bags and no
  event, time, or trace limit;
- zero safety, conflict, stale-arbitration, full A*, global scan, future-route,
  service-overlap, duplicate reservation/grant, permanent-starvation, or final
  pending-state violation;
- at least one real external `53->49 EDGE_ENTER` per scale with exactly one
  released, live local node-49 source winner and uniquely reconstructable
  service episodes.

The qualifying threshold remains at least one per scale. The stale threshold
remains exactly zero. Lifecycle telemetry may use only the already frozen
sub-epsilon logical reconstruction; missing/duplicate states, identity or
grant drift, and reversals greater than epsilon remain fail-closed.

## 6. Promotion order remains closed

Only a formal V3R7 G31 control PASS permits the unchanged synthetic Stage 0
and fixed 120 Stage 1 cases. Only their GO permits the exact V3R7 Nanning rows
to run once with the final clean G32 binary in shadow mode. Only a two-scale
shadow GO may authorize a separately frozen P1 action implementation/review.

V3R7 changes no runtime algorithm, action, map, workload row, threshold,
service value, or closed-loop policy. It replaces a load-induced evidence
cohort with one fixed, outcome-blind, minimum-size causal slice and adds no
runtime branch or map-ID special case.
