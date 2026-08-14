# G4IRSF23 precursor Route Pilot

Status: **NO_GO_PRECURSOR_PILOT_SUPPORT**

The Pilot reuses the existing G22 S4/J2/E2 runtime and exact G21 Route action seam.
For system-panel actions, one complete H_system branch also supplies the same
action's direct H_bag evidence; no duplicate replay or new planner is introduced.
The published raw pairs used a runtime-only ordinary-baseline reuse shortcut
whose checkpoint-continuation outcomes were equivalence-audited. The shipped
runtime omits that unused shortcut and keeps ordinary G22 per-target semantics.

- attempted groups: 512
- complete H_bag groups: 512
- complete H_system groups: 256
- action-changing groups: 512 (1.000)
- fair promotion groups: 6
- system-beneficial groups: 6
- system-beneficial-but-costly groups: 6
- individually fair actions: 512
- strict-no-delay actions (diagnostic): 0
- block-8 fair promotion groups: 0
- fair promotion strata: 4

## H_system effect distribution

- planned H_system actions: 512
- complete H_system actions/groups: 512 / 256
- fair promotion actions/groups: 6 / 6
- deltas are treatment minus baseline; mean TTH/source/network rows are seconds per complete raw bag
- current-bag cost and deadline headroom are seconds for the treated bag

| Metric | Panel min | mean | median | max | Promotion min | mean | median | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| raw-bag mean TTH delta | -8.530958395 | +0.979877288 | +0.000021925 | +23.860560058 | -8.530958395 | -3.609646215 | -3.885528485 | -0.016610538 |
| source-wait mean delta | -3.871171859 | +0.872872707 | +0.000000000 | +19.157225672 | -3.871171859 | -1.988924115 | -2.517682681 | +0.000000000 |
| network-time mean delta | -6.522600505 | +0.107004582 | +0.000021925 | +4.703334386 | -6.522600505 | -1.620722099 | -0.858521013 | -0.016610538 |
| raw-bag p95 delta | -54.432500000 | +6.376816406 | +0.000000000 | +150.747500000 | -54.432500000 | -26.384166667 | -31.782500000 | +0.000000000 |
| raw-bag p99 delta | -9.378500000 | +1.347072266 | +0.000000000 | +24.893500000 | -9.378500000 | -5.785083333 | -8.444000000 | +0.000000000 |
| raw-bag max delta | -95.800000000 | +12.210058594 | +0.000000000 | +532.000000000 | +0.000000000 | +86.266666667 | +68.600000000 | +238.000000000 |
| current-bag completion cost | +0.150000000 | +249.969238281 | +38.425000000 | +5344.400000000 | +112.000000000 | +753.050000000 | +808.425000000 | +1495.400000000 |
| pre-action deadline headroom | +3632.169260706 | +8160.879495081 | +7398.444260706 | +14176.419260706 | +4968.629260706 | +6019.839260706 | +5721.749260706 | +8263.419260706 |

## Gates

- `h_bag_group_coverage`: PASS
- `h_system_group_coverage`: PASS
- `action_changing_rate`: PASS
- `fair_promotion_group_count`: NO-GO
- `block8_fair_promotion_group_count`: NO-GO
- `fair_promotion_strata_coverage`: PASS

## Fixed effect boundary

- usable raw-bag mean gain: at least 0.01 s
- strong raw-bag mean gain: at least 0.05 s
- p95/p99 tolerance: +0.001 s
- max is a separate diagnostic at +0.001 s; it is not a promotion hard gate
- strict no-delay (direct <= +0.001 s) is diagnostic, not the sole fairness gate
- individual fairness uses the pre-action baseline-candidate deadline headroom and the treatment current-bag outcome
- deadline misses may not increase
- only an eligible action can be selected; otherwise the group remains S4

## Exact-pair audit

- manifest shards: 31
- exact execution pairs: 1024
- exact pair gate: PASS_EXACT_PAIR_GATE
- raw branch payloads remain runtime-only and are not committed
