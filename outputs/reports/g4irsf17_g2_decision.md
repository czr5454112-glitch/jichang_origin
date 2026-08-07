# G4IRSF17 G2 decision

Decision: **`CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT`**.

- Phase-A downstream merge/capacity share: **100.00%**.
- G2 pivot triggered: **True**.
- Real 64+ opportunity G2 causal authorization gate: **NOT_RUN/NO_EVIDENCE**.
- G2 causal evidence artifact status: **COMPLETE_MATCHED_SCREEN_NOT_SAME_STATE_CAUSAL**.

Matched bags **4898**; H5−off source wait **+0.149551 s/raw bag**, network time **-0.058518 s/raw bag**, total TTH **+0.091033 s/raw bag**, and positive additional source wait **732.500 s**.

## Completed M1–M6 matched screen

The native screen completed **20 comparisons**: M1 versus M2–M6 at 144, 512, 2,048, 8,192 segments.

- Exact competitive boundary count was zero in every baseline and candidate arm: **True**.
- All matched mean TTH/source-wait/network deltas were exactly zero: **True**.
- Hard safety passed **20/20** comparisons.
- Same-state causal opportunities: **0**; causal follow-up shortlist: **0**.
- Causal authorization remains **False**.

The zero deltas are not evidence that M1-M6 have equivalent successful performance. They occurred with zero exact competitive boundaries, so the current eager-token action seam never exposed a grant choice on which the rules could differ. Hard-safety PASS is an engineering result, not causal performance authorization.
Evidence scope: **`CURRENT_EAGER_SEAM_DIAGNOSTIC_COMPLETE`**. This completes only the current eager-token seam diagnostic, not a global G2 scientific no-go; the bounded JIT choice seam remains unimplemented.

Next pivot: **strictly-local just-in-time service-slot arbitration over a bounded pending set**.

A source-wait attribution pivot is not a G2 performance result. A G2 candidate may enter the matched ladder only after a real causal pilot and hard-safety gate pass.

Evidence: `outputs/tables/g4irsf17_source_wait_topology_attribution.csv`, `artifacts/manifests/g4irsf17_system_campaign_plan.json`, `outputs/tables/g4irsf17_g2_matched_pilot.json`
