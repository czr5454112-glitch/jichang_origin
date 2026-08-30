# G4IRSF32 V3R10 pair-binding addendum

Revision: `G4IRSF32_V3R10_PAIR_BINDING_P0_20260829`

Campaign: `G4IRSF32_V3R10_P0_CAMPAIGN_20260829`

This addendum is frozen before the V3R10 code change or execution. The V3R9
synthetic PASS and composer NO-GO remain immutable evidence.

## Scope

V3R9 passed Stage0 and both Stage1 cohorts. Composer deep replay then rejected
valid repeated-bag diagnostics because it required every source observation
value to remain identical in its joined pair. The join contract intentionally
sets the derived `H_gap` and `X_insert` fields to null for a non-primary
`V3R2_REPEATED_BAG_DIAGNOSTIC`; the existing pair validator separately requires
that exact status, reason, null projection, full schema, and primary arithmetic.

V3R10 changes only source-to-pair binding: identity and equality are checked on
source fields excluding `JOIN_PAIR_KEYS`, after which the unchanged joined-pair
validator checks all join-derived fields. Unknown, duplicate, missing, reordered,
or arithmetically invalid pairs still fail.

There is no change to C++, scheduling, maps, runtime policy, the 120+24 case
population, bootstrap configuration, thresholds, or outer-AND gate logic.

## Registered outputs

- `outputs/tables/g4irsf32_v3r10_synthetic_stage01.json`
- `outputs/reports/g4irsf32_v3r10_synthetic_stage01.md`
- `outputs/tables/g4irsf32_v3r10_p0_campaign.json`
- `outputs/reports/g4irsf32_v3r10_p0_campaign.md`

The Nanning control remains the frozen V3R7 artifact. P1 is authorized only if
the complete V3R10 synthetic result and the registered Nanning 1x/2x shadow both
pass.
