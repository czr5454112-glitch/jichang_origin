# G4IRSF23 externality neighborhood

Status: `NO_GO_EXTERNALITY_NEIGHBORHOOD_SUPPORT`.

The preregistered intervention is only `node 16: S4 17 -> NEXT_EDGE 21` under `G22_S4_J2_E2`, evaluated at `H_system`. Selection used alternate one-hop target queue >= 16 in blocks 22-29, binned as q16_23, q24_31, and q32_plus. No WAIT, H_bag, planner, or learned model was added.

System benefit and individual fairness are orthogonal. Individual fairness reuses the frozen precursor contract: pre-action deadline headroom plus a completed, non-failed treatment current bag finishing by its deadline. No post-hoc direct-cost cap is applied.

The 256-group panel is an outcome-free execution panel. A native `SCREENING_FALSE_POSITIVE / NOT_APPLICABLE_ACTION_PRECONDITION_FAILED` is reported as a completed guard abstention, not as an action-changing certificate. Effect, fairness, and held-out calculations use applied action-changing pairs only.

| Item | Value |
|---|---:|
| Attempted H_system groups | 256 |
| Identity-covered executions | 256 |
| Missing / unknown executions | 0 / 0 |
| Applied action-changing groups | 243 |
| Native guard abstentions | 13 |
| Action-changing rate | 0.949219 |
| Guard-abstain reasons | `{"NOT_APPLICABLE_ACTION_PRECONDITION_FAILED": 13}` |
| Effect-complete applied groups | 243 |
| System-safe groups | 61 |
| System-beneficial groups | 17 |
| System-beneficial block x one-hop queue cells (fairness not required) | 10 |
| Fair system-beneficial groups | 17 |
| Fair system-beneficial block x one-hop queue cells (continuation coverage) | 10 |
| System-beneficial but costly groups | 15 |
| System-beneficial but unfair groups | 0 |
| Selected discovery pressure bin | `q24_31` |
| Held-out local signature | False |
| Raw-bag max delta, diagnostic only (count/min/mean/median/max s) | 243 / -165.8000000000029 / 45.610493827158095 / 0.0 / 596.0 |

| Continuation gate | Pass |
|---|---:|
| 256/256 execution identity coverage | True |
| All execution outcomes recognized | True |
| Action-changing rate >= 0.80 | True |
| At least 20 fair system-beneficial actions | False |
| At least 3 fair system-beneficial block x one-hop queue cells | True |
| System-only discovery 22-25 -> held-out 26-29 signature | False |

The held-out signature is preregistered on system benefit only; it does not use or claim individual-fairness replication. Fair cell coverage is a separate continuation gate. The system tail hard gate uses p95/p99 only; raw-bag max delta remains a reported diagnostic and cannot change system-safe, system-beneficial, or continuation status.

## Runtime audit boundary

- manifest shards: 64
- identity-covered execution attempts: 256
- action-changing pairs: 243
- native guard abstentions: 13
- execution/applicability gate: PASS_EXECUTION_COVERAGE_AND_ACTION_CHANGE_GATE
- runtime-only artifact; publication requires an explicit later review
