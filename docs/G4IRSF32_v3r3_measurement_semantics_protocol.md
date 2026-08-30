# G4IRSF32 V3R3 measurement-semantics and Nanning P0 protocol

Protocol ID:
`G4IRSF32_EXTERNAL_COMMIT_LOCAL_VIRTUAL_SLOT_SHADOW_P0_V3R3`.

Implementation parent and audit base:
`46cc46ab6bc121628fd6357e9f3c7636745fd732`.

Frozen `2026-08-27` (Asia/Shanghai), before any formal V3R3 case or Nanning
G32 selection/outcome run. Status:
`FROZEN_PROTOCOL_ONLY_NO_V3R3_DATA_RUN`.

This is a minimal measurement-semantics revision of the frozen
`G4IRSF32_v3r2_minimal_protocol.md`. It does not change the V3R2 native
observation hypothesis, fixed 120-case population, release schedule, X/Y
estimand, statistical thresholds, resource ratio, action-inertness, map2
sentinel, mode set, runtime policy, or algorithm. Unless this document says
otherwise, every V3R2 clause remains binding.

## 1. Preserved V3R2 negative record

V3R2 is not retroactively declared GO. Its zero-`starvation_count` gate is
`NO_GO_V3R2_PROTOCOL_INFEASIBLE_STARVATION_PROXY` for the frozen population.
The native counter is incremented for a completed bag whose finite
`total_wait` is strictly greater than the unchanged 120-second legacy
threshold. It does not mean that a reachable bag was permanently denied
service.

For the frozen single-L-server `local_only,n=128,s=1` control, all bags are
released at zero and require one second at L. Even an ideal work-conserving
schedule has wait slots 0 through 127 seconds, so seven completed bags must
have wait greater than 120 seconds. At service values 1.5, 2, and 3 seconds,
the same capacity lower bound is stronger. No action-inert shadow
implementation can make this legacy diagnostic zero without changing the
population, service capacity, threshold, or accounting.

This contradiction was identified by source audit and bounded focused
diagnostics before any formal 120-case V3R3 run. V3R3 must not delete the V3R2
protocol, its ledger entries, or the focused counts.

## 2. Unchanged experiment and thresholds

V3R3 uses, byte for byte, the V3R2:

- four services `{1.0,1.5,2.0,3.0}`;
- three populations `{8,32,128}`;
- ten ordered flow patterns and their exact releases;
- 120-case order, task IDs, segment IDs, deadlines, profiles, and requests;
- `off|shadow` modes with default `off` and no action/event mutation;
- DIRECT/J2 seams, fixed-row sidecar, map2 sentinel, future/distant probes,
  exact-off, rollback, locality, census, service, resource, and identity gates;
- X/Y join, at least 24 directional cases, 128 unique primary bags, four
  mixed flows, all services and populations;
- mean Spearman rho `>0`, 2.5% case-bootstrap lower bound `>0`, at least 60%
  positive cases, and Wilson lower bound `>0.5`;
- seed `3200260827`, 10,000 draws, epsilon `1e-9`, and every resource ratio
  `<=1.10`.

The V3R2 native row/schema name remains unchanged because the observation is
unchanged. V3R3 adds no production mode and authorizes no P1 action by itself.

## 3. Exact local winner clarification

The fixed numeric row also binds the existing local controller scalar
`local_escape_token_runtime_bag_id`. This is an observation of existing state,
not new state.

Offline validation reconstructs L's source queue from the complete ordinary
`LOCAL_QUEUE_UPDATE` history at the observation event. It then replays the
existing `choose_bag` rule exactly:

1. if the nonnegative escape-token runtime bag is present in that source
   queue, choose its exact queue index;
2. otherwise choose frozen FIFO by `(source_enqueued_at,runtime_bag_id)`.

The row's choose index, selected local runtime bag, and enqueue time must match.
Token values below `-1`, incomplete queue history, or any mismatch fail the
case. A global escape activation count is never used as a proxy for this local
state.

## 4. Legacy wait-over-120 diagnostic

The native 120-second threshold, summary `starvation_count`, per-bag `starved`
flag, and wait accounting remain unchanged and are never hidden.

For each off and shadow case, the evidence layer must independently recompute:

```text
legacy_wait_over_120(bag) = finite(total_local_wait) > 120.0
legacy_wait_over_120_count = sum(legacy_wait_over_120(bag))
```

Hard gates require:

- every native bag flag equals the independent comparison;
- the native summary count equals the independent bag count;
- off and shadow counts, ordered flags, waits, bag identities, and per-origin
  counts are exact;
- the full per-case and per-origin counts, maximum waits, ordered-vector hash,
  and legacy threshold are retained in JSON evidence.

The legacy count is diagnostic and may be positive. P0 requires exact
off/shadow equality. A later P1 candidate may not increase it relative to its
paired control, but a zero value is not substituted for the permanent-
starvation definition below.

## 5. Permanent-starvation hard gate

The original action plan prohibits permanent starvation. For a finite,
topology-reachable case, `permanent_starvation_zero` passes only if all of the
following are true in both off and shadow:

- requested count equals the frozen population and every requested runtime
  bag identity appears exactly once;
- every bag completes exactly once, has finite finish time not later than its
  frozen deadline, and receives exactly one L service where applicable;
- failed count, final active-bag count, unresolved deadlock count, event-limit
  flag, and time-limit flag are zero/false;
- every junction's final source queue and final ordinary queue are empty;
- final scheduled incoming is zero at every junction;
- final merge pending, outstanding, and active-unconsumed grants are zero;
- for each mixed case, completed counts for `local` and `external` equal their
  exact requested counts.

No numeric run-length, share, or origin-balance threshold is introduced. The
L service episode sequence is sorted deterministically and must conserve every
bag and origin exactly, without reuse or overlap. Its origin sequence hash and
maximum consecutive origin run are reported as diagnostics, not selected
after outcomes.

## 6. Nanning P0 control-selected shadow slice

Synthetic Stage 0/1 and the map2 sentinel are not sufficient to authorize a
P1 action. After the synthetic 120-case relationship passes, but before any
`closed_loop` mode is specified or implemented, V3R3 must prove that the
registered mixed-origin state occurs in an outcome-blind Nanning slice.

### 6.1 Frozen sources

- G31 base commit:
  `46cc46ab6bc121628fd6357e9f3c7636745fd732`;
- G31 Release pyd SHA-256:
  `35A43037B0881ACA3B92732541126EE71C2D431D537A13E07918777C8B7CCE59`;
- Nanning profile SHA-256:
  `70AEEAFE2C774D415FE9F922EEDEC36E8E35132BCBA04596C2B1C486FFB3D1DF`;
- canonical source workload SHA-256:
  `968D2C876FCBF03C5B25C8E865CCD469431AF3DDBF59DC9EBE073752BD93678F`;
- legacy source timetable SHA-256:
  `0F39D359B47A3F243AB077E4A294CBAB56EC306A0F89BCC0CCC1D946CACEEF87`;
- 1x manifest SHA-256:
  `6D097CA9DDF6975DD79FDAA04D5E68276864BBDC790AC67A947FFC24F5D13DE1`;
- 2x manifest SHA-256:
  `4B86C684F15F02F967E2477860150145EBB34DF6A10174FCDE1077A3500EAE2E`;
- committed G31 Nanning aggregate SHA-256:
  `2BD68C9007FDA73D93EFD25200FF7FADD9D516E08ADBCBB33DD777F8168A72DA`.

The two registered cases are 1x and 2x, stable 2.5 m/s, with no faults.

### 6.2 Outcome-blind row selection

For each scale, regenerate the canonical G31 workload and first verify the
frozen counts: 28,506 raw/43,603 segments for 1x and 57,012 raw/87,206
segments for 2x.

Define:

- external pool E: `start=53` and segment suffix `:storage_out`;
- local pool L: `start=49`;
- projected external arrival at node 49:
  `external_release + 150.25/2.5 + 0.001` seconds.

The length 150.25 is the frozen directed profile edge `53->49`; 0.001 is the
already-frozen positive runtime minimum at the zero-service start.

Rank every E/L pair by:

```text
(abs(local_release-projected_external_arrival),
 max(external_release,local_release),
 external_segment_id,
 local_segment_id)
```

Greedily take the first 32 pairs without reusing either segment, retain all 64
segments, and order the selected rows by
`(pass_time,segment_id,task_id)`. No row may be removed after a control or G32
result is seen.

### 6.3 G31 control-only selection gate

Before any G32 Nanning run, execute the exact selected rows with the frozen G31
Release binary in omitted/off mode and full ordinary traces. Write a new,
append-only control-selection JSON that binds regenerated workload hashes,
selected rows, request/profile/potential/binary hashes, exact ordinary events,
decisions, service episodes, and their canonical hashes.

Each scale must contain at least one real committed external `53->49` entry at
an epoch where node 49 has a distinct released/live local source-queue winner.
The two bags must complete; node-49 service intervals must not overlap. The
entire 64-segment slice must complete with zero failed, conflict, unsafe,
runtime full A*, global scan, trace/lifecycle truncation, unresolved deadlock,
or final pending state.

If either scale has zero qualifying control events, the verdict is
`NO_GO_NANNING_P0_CONTROL_SELECTION_NO_EVENT`; G32 Nanning and P1 action work
must not start.

### 6.4 G32 shadow gate

Only after the control-selection artifact is frozen may the same ordered rows,
profile, potential, request, speed, horizon, and no-fault condition execute in
G32 shadow mode. The only request difference is the shadow mode and its trace
limit.

Off/shadow ordinary state must be exact. Every admitted row must pass the same
V3R3 identity, winner, census, service, locality, resource, and join gates. Each
scale must admit at least one `node=49, external_upstream_node=53` row. Otherwise
the verdict is
`NO_GO_NANNING_P0_REAL_MIXED_ORIGIN_NOT_OBSERVED`, and P1 remains forbidden.

## 7. V3R3 decision

The P0 relationship may authorize a separately frozen P1 action review only
when Stage 0, all 120 synthetic cases, and both Nanning control-selected shadow
slices pass every unchanged or revised hard gate.

The only GO label is:

`GO_V3R3_EXTERNAL_COMMIT_LOCAL_VIRTUAL_RELATION_AND_NANNING_P1_REVIEW_ALLOWED`.

Any failure is retained with a specific NO-GO label. It cannot be repaired by
raising 120 seconds, changing the fixed 120-case releases, dropping cases,
shrinking the Nanning pool after outcomes, weakening statistical/resource
thresholds, or implementing P1/B/C before a fresh protocol is frozen.

