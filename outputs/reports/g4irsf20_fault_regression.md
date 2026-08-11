# G4IRSF20 event-hotpath fault regression

Campaign status: **`COMPLETE`**.

This matched regression keeps A0 + S4 + J2 (M3 destination-grant rule) and two protected 8,192-segment-prefix fault cases fixed. Only the event-hotpath policy changes.

| Scenario | Policy | Complete E0/new | Physical entries E0/new | Affected complete E0/new | Bounded action projection equal | Per-task TTH equal | Event delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| pending_inflight_repair | E2 | COMPLETE/COMPLETE | 0/0 | 10/10 ; 10/10 | True | True | -145629 |
| inflight_exact_lease_repair | E2 | COMPLETE/COMPLETE | 0/0 | 3/3 ; 3/3 | True | True | -145645 |

## Claim boundary

The comparison covers immediate fault notifications only. Delayed and dropped notification behavior remains explicitly unevaluated in G4IRSF20; notification counters are descriptive and are not used as proof for that case.

Per-bag final/count/last-eight action projections and complete timing projections were compared in memory and were not persisted; this is not a full action-trace claim.
