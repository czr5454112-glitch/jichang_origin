# G4IRSF22 evidence-bound idea log

This log records ideas created or revised during G22. An idea is not a runtime
feature unless exact evidence explicitly authorizes it.

## Accepted implementation ideas

### One explicit 2x research profile

Use `G22_S4_J2_E2` instead of weakening G20's protected 1x gate or ignoring a
hard-gate result in Python. The profile keeps S4/J2/E2 fixed and changes only
the expected formal census shape to 57,012 raw bags / 87,206 segments.

Result: accepted. All 128 H_system treatments completed at the formal 2x shape
and passed row-level live/formal/hard gates. G15/G20 semantics remain intact.

### Separate direct-bag and full-system contracts

Keep H_bag utility as direct affected-bag gain, but compact H_system only from
the full 57,012-raw-bag cohort metrics. Never reuse the direct completion delta
as system utility.

Result: accepted. This separation exposed the decisive externality: among 22
direct-positive actions, 16 made the system mean worse, one was neutral, and
four more improved the mean while regressing a tail. Only one was mean-and-tail
safe, with a very small `0.003310 s/raw bag` system gain.

### Compact branch-local future accumulator

Measure 5/15/30/60-second queue area, scheduled incoming area, next-service
deficit, and queued wait inside exact offline branches. Do not save a full
future trace or expose the summary to the online scorer.

Result: accepted as research instrumentation. Endpoint integration uses
half-open intervals and earliest-next-service semantics. A true node-local
service-completion counter was not available, so completion is explicitly
marked unavailable instead of being inferred from reservation expiry.

### Route-decision-sampled congestion episodes

Use rich I3 rows and fixed 16/8 hysteresis before adding telemetry. Preserve a
bounded sample plus the full affected-row count.

Result: accepted for detection. The census produced 339 sampled episodes
across 12 owners, 19 time blocks, and all three legs. The descriptors remain
descriptive; no heap scan, global snapshot, or telemetry supervisor is added.

### Unsupported strata stay unsupported

Select only strata with an explicit score above `1e-9`, prioritize the score,
and keep runtime bags unique. Do not manufacture calendar-wait or S4/v2
divergence coverage from numerical noise.

Result: accepted. The 256 attempted groups contain 128 high-target-queue and
128 high-merge-contention states. Calendar/divergence strata are reported as
unsupported.

## Tested and rejected ideas

### Broad current-point Route replacement

Result: rejected as runtime guidance. Of 332 complete non-S4 H_bag treatments,
22 were beneficial, 215 harmful, and 95 neutral. In the outcome-informed
H_system veto panel, the 22 positives averaged a `+2.951204 s/raw bag`
treatment-minus-baseline regression.

This does not say all current actions are useless. It says rare direct wins do
not provide a safe general selector.

### Direct affected-bag gain as the policy objective

Result: rejected. Large direct wins frequently transferred delay to Source or
the downstream cohort. A `+1,189.25 s` direct win caused a
`+13.931651 s/raw bag` system mean regression, with p95/p99 regressions of
`83.79/12.872 s`.

### Fixed local-future cost as a deployable selector

The tested cost adds exact local queue area, scheduled-incoming area,
horizon-normalized service deficit, and queued wait, then requires three of
four horizons to agree.

Result: rejected. Across 166 groups, consensus selected 123 non-S4 actions but
only 8 were beneficial and 67 harmful; mean gain was `-1.957831 s`. Individual
horizon beneficial precision was only about 5.8%-6.6%.

This rejects the fixed formula, not local information in principle. It is not
a perfect-information upper bound and has no held-out validation.

### Generic congestion detour-release rule

Result: rejected as runtime guidance. The earlier small screen was
post-selected and not held out; its apparent direct positives were not stable
under H_system mean and tail checks. It is not used as final evidence.

### Attribute the remaining gap to Merge

Result: rejected. S4 merge wait is a subset of inclusive Route wait and v2 has
no comparable J2 grant instrument. J2 is already the verified simple JIT merge
mechanism, so the ledger cannot honestly authorize more Merge ownership.

## New verified hypotheses

### Cohort relief may require an individually costly action

Two exact rows improved full-system mean and tails while hurting the acting
bag:

- event 2084094, edge 21: direct `-257.10 s`, system mean `-1.812684 s/bag`,
  p95/p99 `-23.31/-7.8895 s`;
- event 1268733, edge 21: direct `-437.80 s`, system mean `-1.189311 s/bag`,
  p95/p99 `-26.0725/0 s`.

Interpretation: the useful objective may be a bounded local congestion price,
not the acting bag's immediate completion gain. Status: evidence-backed
hypothesis only. Before any runtime use it needs an explicit individual-delay
cap/fairness contract, an outcome-free local signature, and held-out exact
validation. Do not train from these two rows.

### Action freedom exists, selection is the bottleneck

The outcome-only perfect-action ceiling over complete groups is
`+62.504819 s/group`, while the fixed local-cost screen is negative. This means
the action seam is not empty; the current simple local objective cannot
identify the useful action reliably.

Status: recorded, but it does not unlock a model. Outcome utility is never an
oracle or runtime input.

### Source timing is the strongest next seam

The matched raw-bag bank assigns `+54.666355 s/bag` to Source wait. In the
segment diagnostic, storage_out has `+89.205289 s/segment` Source delta. The
true storage-out admission node is `node_52`; release block 7 has 3,600
segments with `+583.655486 s/segment` Source delta, and block 8 is the smaller
confirmation cell.

Status: strongest next experiment. It replaces the earlier, incorrect mix of
task-origin nodes 53/1/2/0 with the actual storage-out seam.

## Next smallest experiment

Run exact Source counterfactuals only for storage_out at `node_52`, block 7,
with block 8 confirmation:

- reuse the existing Source opportunity/checkpoint interface;
- compare ADMIT-current-front with HOLD-one-natural-opportunity;
- continue unchanged with S4/J2/E2;
- screen H_bag, then require stable H_system mean, p95, and p99;
- add no top-K reorder, supervisor, global queue, future route, or eager token
  reservation.

G16's broad Source policy remains rejected. This narrow test must earn its own
authorization.

## Secondary diagnostic

Storage_in carries `+88.947820 s/segment` of Route-wait delta. Keep it behind
the Source test. The current-point H_system veto does not justify another
Route model now, and the tiny precursor observation is not a universal
precursor no-go.
