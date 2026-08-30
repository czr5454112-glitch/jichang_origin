# G4IRSF32 V3R11 deep-replay compatibility addendum

Revision: `G4IRSF32_V3R11_DEEP_REPLAY_COMPATIBILITY_P0_20260829`

Campaign: `G4IRSF32_V3R11_P0_CAMPAIGN_20260829`

This addendum is frozen before the V3R11 implementation commit and formal
execution. All V3R8–V3R10 artifacts remain immutable.

## Scope

V3R10 passed Stage0 and both Stage1 cohorts. A read-only full replay of that
artifact identified exactly two remaining loader/producer compatibility gaps:

1. The frozen Stage0 `j2` role was rebuilt with the default direct request,
   omitting its real node 4. Replay must pass `j2=true` only for that registered
   role.
2. The runner's map2 identity contains `segments` and `storage_source_nodes` in
   addition to four digests. Replay must require all six exact keys and compare
   all six values with a freshly rebuilt frozen map2 fixture.

V3R11 retains the V3R10 source-to-pair fix and makes only those two changes.
With them, the existing immutable V3R10 synthetic artifact completes the whole
deep loader successfully; no additional mismatch was observed.

There is no change to C++, runtime policy, scheduling, maps, release geometry,
the 120+24 population, statistics, thresholds, or outer-AND gates.

## Registered outputs

- `outputs/tables/g4irsf32_v3r11_synthetic_stage01.json`
- `outputs/reports/g4irsf32_v3r11_synthetic_stage01.md`
- `outputs/tables/g4irsf32_v3r11_p0_campaign.json`
- `outputs/reports/g4irsf32_v3r11_p0_campaign.md`

The Nanning input remains the frozen V3R7 control. P1 is authorized only by a
complete V3R11 FINAL_GO after synthetic and registered Nanning shadow both pass.
