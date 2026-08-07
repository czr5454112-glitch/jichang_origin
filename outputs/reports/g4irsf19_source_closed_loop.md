# G4IRSF19 Source closed-loop boundary

Status: `NOT_A_LEARNED_CLOSED_LOOP_CAMPAIGN`.

A0/A1/A2 are deterministic configurations of the existing native ADMIT/HOLD pressure gate. They test whether the seam is active and whether its business effect is promising; they do not evaluate a learned Source policy and therefore cannot establish learned Source ownership or action mutations.

| Case | Arm | Safety | Downstream HOLD retries | Distinct observed HOLD states | Delta TTH vs A0 (s) | Delta source wait vs A0 (s) |
|---|---|---|---:|---:|---:|---:|
| prefix_144 | A1 | True | 30 | 30 | 0.0005 | 0.2986 |
| prefix_144 | A2 | True | 30 | 30 | 0.0005 | 0.2986 |
| prefix_512 | A1 | True | 137 | 137 | 0.0946 | 0.7568 |
| prefix_512 | A2 | True | 137 | 137 | 0.0946 | 0.7568 |
| scale_2x | A1 | True | 57528 | - | 7.7638 | 11.8596 |
| scale_2x | A2 | True | 35385 | - | 4.9372 | 4.1127 |

HOLD retries are repeated admission evaluations, not distinct bag mutations. The distinct-state column is still only observed seam activity, not a cloned counterfactual action count.

Promotion remains blocked until a bounded learned ADMIT/HOLD policy changes actions on matched states and passes the paired safety and business gates. This report intentionally records that boundary instead of relabeling deterministic pressure gating as learning.
