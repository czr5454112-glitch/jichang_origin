# G4IRSF18 scale capacity

Status: **`BLOCKED_BY_4X_WALL_BOUNDARY`** (9/18 jobs).

1x–16x use the complete G10 distribution-preserving stream. 32x is an explicit 8,192-segment smoke. Every launched scale row uses capacity mode (opportunity rows disabled). A wall-censored row is a resource-boundary observation: it is never ranked as a performance win and does not adjudicate algorithm safety.

| Scale | Arm | Scope | Status | Capacity cause | Completed | Algorithm safety | Mean TTH s | Δ vs J0 s | Δ vs J1 s | Events/bag | Pending peak | Wall s | Wall cap s | CPU lower bound s | RSS MB |
|---:|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1x | J0_F2_EAGER | full | COMPLETE | COMPLETE_NO_CAPACITY_CENSORING | 43603/43603 | True | 217.467307 | — | — | 186.211359 | 2 | 30.259 | — | — | — |
| 1x | J1_F2_JIT_FIFO | full | COMPLETE | COMPLETE_NO_CAPACITY_CENSORING | 43603/43603 | True | 214.905057 | -2.562250 | — | 171.700589 | 6 | 28.146 | — | — | — |
| 1x | J2_F2_JIT_FAIR_AGING_DEADLINE | full | COMPLETE | COMPLETE_NO_CAPACITY_CENSORING | 43603/43603 | True | 214.944726 | -2.522581 | 0.039669 | 171.645408 | 7 | 27.161 | — | — | — |
| 2x | J0_F2_EAGER | full | COMPLETE | COMPLETE_NO_CAPACITY_CENSORING | 87206/87206 | True | 1394.708896 | — | — | 263.639251 | 2 | 159.012 | — | — | — |
| 2x | J1_F2_JIT_FIFO | full | COMPLETE | COMPLETE_NO_CAPACITY_CENSORING | 87206/87206 | True | 959.393343 | -435.315553 | — | 222.336771 | 8 | 101.110 | — | — | — |
| 2x | J2_F2_JIT_FAIR_AGING_DEADLINE | full | COMPLETE | COMPLETE_NO_CAPACITY_CENSORING | 87206/87206 | True | 851.864109 | -542.844788 | -107.529234 | 223.906932 | 9 | 93.431 | — | — | — |
| 4x | J0_F2_EAGER | full | WORKER_TIMEOUT_CENSORED | WORKER_WALL_TIMEOUT | —/174412 | None | — | — | — | — | — | — | 1200.000 | 1199.844 | 770.453 |
| 4x | J1_F2_JIT_FIFO | full | WORKER_TIMEOUT_CENSORED | WORKER_WALL_TIMEOUT | —/174412 | None | — | — | — | — | — | — | 1200.000 | 1154.875 | 770.344 |
| 4x | J2_F2_JIT_FAIR_AGING_DEADLINE | full | WORKER_TIMEOUT_CENSORED | WORKER_WALL_TIMEOUT | —/174412 | None | — | — | — | — | — | — | 1200.000 | 1151.969 | 741.488 |

## Incremental boundary

Progression-blocked: 9 job(s): `j0_f2_eager__8x_full`, `j1_f2_jit_fifo__8x_full`, `j2_f2_jit_fair_aging_deadline__8x_full`, `j0_f2_eager__16x_full`, `j1_f2_jit_fifo__16x_full`, `j2_f2_jit_fair_aging_deadline__16x_full`, `j0_f2_eager__32x_smoke8192`, `j1_f2_jit_fifo__32x_smoke8192`, `j2_f2_jit_fair_aging_deadline__32x_smoke8192`.
The matched 4x arms exhausted the external wall boundary without a native return; 8x/16x full and 32x smoke are intentionally not launched and have no synthesized metrics.
