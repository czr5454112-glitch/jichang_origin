# G4IRSF19 J2/S4 fault evidence

Campaign status: **`COMPLETE`**.

This is a paired 8,192-segment regression over the protected G18 fault catalogue. S1 and S4 share J2/M3 and every other runtime control; only the one-hop Route scorer changes.

Raw opportunity rows persisted: **0**.

| Scenario | Hard safety S1/S4 | Physical entry violations S1/S4 | Notification updates S1/S4 | Drops S1/S4 | Recovery s S1/S4 | ΔTTH s | Δsource wait s | Δmerge wait s | Δevents |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pending_inflight_repair | True/True | 0/0 | 361290/359950 | 0/0 | 65.272/65.272 | -1.794 | -0.226 | -0.114 | -3269 |
| inflight_exact_lease_repair | True/True | 0/0 | 361283/359943 | 0/0 | 67.651/67.651 | -1.794 | -0.226 | -0.114 | -3269 |

## Claim boundary

A negative delta means S4 used less time or fewer events than S1 on the same protected input and fault window. Missing recovery values remain missing; they are not imputed. This campaign is fault evidence for the existing decentralized one-hop scorer, not a production promotion decision.
