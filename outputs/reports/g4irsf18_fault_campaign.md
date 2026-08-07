# G4IRSF18 fault/repair campaign

Status: **`COMPLETE`** (6/6 jobs).

The 35% window validates pending-wait preservation. A second, evidence-directed window targets the midpoint of an observed edge-(6,12) grant flight and validates exact-lease recovery. J0 is the fault-safety control; J1/J2 carry the mechanism gates.

| Scenario | Arm | Gate | Status | Exposure | Pending | In-flight lease | Fault+repair | Outstanding=0 | Hard safety | Regression | TTH delta vs no-fault s |
|---|---|---|---|---|---|---|---|---|---|---|---:|
| inflight_exact_lease_repair | J0_F2_EAGER | control_fault_safety | COMPLETE | True | False | True | True | True | True | True | 0.001164 |
| inflight_exact_lease_repair | J1_F2_JIT_FIFO | inflight_exact_lease | COMPLETE | True | True | True | True | True | True | True | 0.001162 |
| inflight_exact_lease_repair | J2_F2_JIT_FAIR_AGING_DEADLINE | inflight_exact_lease | COMPLETE | True | True | True | True | True | True | True | 0.001162 |
| pending_inflight_repair | J0_F2_EAGER | control_fault_safety | COMPLETE | True | False | False | True | True | True | True | -0.010937 |
| pending_inflight_repair | J1_F2_JIT_FIFO | pending_wait | COMPLETE | True | True | False | True | True | True | True | 0.001162 |
| pending_inflight_repair | J2_F2_JIT_FAIR_AGING_DEADLINE | pending_wait | COMPLETE | True | True | False | True | True | True | True | 0.001162 |

## Incremental boundary

All preregistered jobs for this stage have a result artifact.
