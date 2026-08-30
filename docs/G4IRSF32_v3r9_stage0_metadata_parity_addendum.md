# G4IRSF32 V3R9 Stage0 metadata-parity addendum

Revision: `G4IRSF32_V3R9_STAGE0_METADATA_PARITY_P0_20260828`

Campaign: `G4IRSF32_V3R9_P0_CAMPAIGN_20260828`

This addendum is frozen before the V3R9 code change or execution. The V3R8
formal NO-GO remains immutable evidence.

## Scope

V3R8 stopped at `shadow_repeat_exact`. The baseline and repeat executions had
identical ordinary payload, shadow extension, joined outcomes, resources, and
four normalized physical rows. Their sole field difference was that the
baseline projection included `cohort=safety_regression`, while the repeat
projection omitted that metadata.

V3R9 makes exactly one semantic-neutral evidence change: the repeated Stage0
row extraction receives the same `cohort=safety_regression` and `replica=null`
metadata as the baseline extraction.

There is no change to C++, scheduling, release geometry, maps, runtime policy,
case population, bootstrap seed/draws, thresholds, or gate logic. The V3R8
dual cohort remains exactly 120 safety-regression cases plus 24 identification
cases.

## Registered outputs

- `outputs/tables/g4irsf32_v3r9_synthetic_stage01.json`
- `outputs/reports/g4irsf32_v3r9_synthetic_stage01.md`
- `outputs/tables/g4irsf32_v3r9_p0_campaign.json`
- `outputs/reports/g4irsf32_v3r9_p0_campaign.md`

The historical Nanning control remains the frozen V3R7 artifact. V3R9 may
authorize P1 only if the unchanged Stage0, both Stage1 cohorts, and the
registered Nanning 1x/2x shadow all pass under the existing outer AND.
