# G4IRSF32 V3R8 identifiable synthetic P0 addendum

Revision: `G4IRSF32_V3R8_IDENTIFIABLE_SYNTHETIC_P0_20260828`.

Frozen on 2026-08-28 (Asia/Shanghai) at source revision `5ba3b3e`, before
building or running any V3R8 executor. V3R7 attempt 1 remains a terminal
identification NO-GO and is not reinterpreted.

## 1. Purpose and scope

The V3R7 Stage 1 safety run completed all 120 registered cases, but its
directional estimand was structurally unidentifiable: within every mixed case,
`X_insert` had only one distinct value. V3R8 changes only the synthetic release
schedule used to identify the already implemented shadow measurement. It does
not change the runtime algorithm, topology, service semantics, map logic,
thresholds, or the later closed-loop candidate.

Stage 1 now has two named cohorts:

- `safety_regression`: the original 120 V3R2 cases, requests, releases, and
  negative controls without modification. These cases must still pass all
  completion, safety, census, exact-off parity, resource, and no-op gates.
- `identification`: 24 fresh mixed-origin cases defined below. Only this cohort
  supplies the case-level directional relationship.

Both cohorts must pass. A directional pass cannot compensate for a safety
failure, and the old 120 cases cannot be pooled to manufacture direction.

## 2. Frozen identification population

The population is the Cartesian product:

- service seconds: `1.0, 1.5, 2.0, 3.0`;
- requested bag counts: `8, 32, 128`;
- replicas: `0, 1`.

This gives exactly 24 cases. Every case uses the existing four-node motif,
one external incoming edge, one local source at service node 1, FIFO, and the
existing `off|shadow` request projection.

Each case has a seven-bag core: local bags `L0..L3` and external bags `E1..E3`.
It is designed to yield three distinct primary pairs `(L1,E1)`, `(L2,E2)`,
and `(L3,E3)`. Cases with population 32 or 128 append external-only filler
bags after the core has drained; fillers are separated by more than two
service quanta and cannot create an additional mixed-origin observation.

The four flow labels are `identification_p0..identification_p3`. For service
ordinal `a`, population ordinal `b`, and replica `r`, the label index is
`(a + b + 2*r) mod 4`. This produces six cases per label without reading any
runtime outcome.

## 3. Integer-time release construction

All design arithmetic is performed in integer microseconds and converted to
seconds only when request rows are created.

Constants:

- initial local service start `S0 = 10,000,000`;
- external travel `d = 50,000`;
- storage service `m = 1,000`;
- delta values `12,500`, `25,000`, `37,500`;
- service quanta `s = 1,000,000`, `1,500,000`, `2,000,000`, or `3,000,000`.

The delta order is fixed by the flow label:

| label | delta order (microseconds) |
|---|---|
| `identification_p0` | `12,500, 25,000, 37,500` |
| `identification_p1` | `25,000, 37,500, 12,500` |
| `identification_p2` | `37,500, 12,500, 25,000` |
| `identification_p3` | `37,500, 25,000, 12,500` |

`L0` releases at `S0`. For segment `j=1..3`, with the previous local service
start `S` and the segment delta `delta[j]`, freeze:

```text
C        = S + s
release(Lj) = S + s/2
commit(Ej)  = C - d + delta[j]
release(Ej) = commit(Ej) - m
arrival(Ej) = C + delta[j]
complete(Ej)= arrival(Ej) + s
next S      = complete(Ej)
```

Thus each external commit occurs strictly before the current local service
completes, while its projected arrival occurs strictly after that completion
and inside the waiting local bag's virtual service slot. Analytically this
gives three distinct positive insertion values `s + delta[j]`. The subsequent
local start is outcome telemetry and is not assumed by the constructor.

After `L3`'s predicted completion, filler `k` releases at
`core_end + 10*s + k*(2*s + 1,000,000)`. Deadlines retain the existing broad
completion margin. Task and segment identities are deterministic and disjoint
from the original 120-case population.

## 4. Unchanged decision gates

The original thresholds are retained:

- exactly 120/120 safety-regression cases and 24/24 identification cases
  attempted with no execution error;
- all requested bags complete once; zero failed, active, late, unresolved,
  overlap, duplicate, stale, global-scan, future-input, or final-pending safety
  violation; original negative controls emit no admitted row;
- off/shadow ordinary behavior and service order remain equal;
- shadow/off resource ratios are at most `1.10` for every registered case;
- at least 24 directional cases, 128 unique primary bags, four identification
  labels, all four services, and all three populations;
- case-equal mean Spearman rho and its fixed case-bootstrap 2.5% lower bound
  are both positive;
- at least 60% of case rhos are positive and the Wilson lower bound is greater
  than 0.5.

The expected structural count is 72 primary pairs and 144 unique primary bag
identities. These expectations do not replace the runtime-derived gates.

## 5. Revision and promotion boundary

- historical Nanning control revision remains
  `G4IRSF32_V3R7_MINIMAL_PREARRIVAL_OVERLAP_NANNING_P0`;
- synthetic revision is
  `G4IRSF32_V3R8_IDENTIFIABLE_SYNTHETIC_P0_20260828`;
- campaign/evidence revision is
  `G4IRSF32_V3R8_P0_CAMPAIGN_20260828`;
- synthetic output paths are
  `outputs/tables/g4irsf32_v3r8_synthetic_stage01.json` and
  `outputs/reports/g4irsf32_v3r8_synthetic_stage01.md`;
- campaign output paths are
  `outputs/tables/g4irsf32_v3r8_p0_campaign.json` and
  `outputs/reports/g4irsf32_v3r8_p0_campaign.md`.

The immutable V3R7 control may be consumed through a narrow compatibility
loader: its recorded V3R7 gates must pass, and the same raw payload must pass
the current read-only audit. It is not rerun or rewritten.

Only a clean committed V3R8 Stage 0 plus both Stage 1 cohorts may start the
registered Nanning G32 shadow. Only the combined two-scale P0 GO may authorize
implementation of Candidate A. A failed run is archived as a new NO-GO and
does not permit threshold or outcome-dependent schedule changes.
