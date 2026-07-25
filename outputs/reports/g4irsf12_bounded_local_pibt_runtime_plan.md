# G4IRSF12 Bounded-Local PIBT Runtime Plan

Status: `PARTIAL_EXECUTION_PENDING_TIERS`.

Every unexecuted case is retained as `NOT_RUN` / `PENDING`. No planned
row is treated as PASS, and incomplete survivor timing is excluded from
comparison.

## Evidence ledger

| Case | Size | R/S/P/C | Fault | Execution | Gate | Complete bags | Segments | Denominator | Blocker |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| F_p1 | 8192 | R3/S0/P1/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| F_p2 | 8192 | R3/S0/P2/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| F_p3 | 8192 | R3/S0/P3/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| F_p4 | 8192 | R3/S0/P4/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| F_p0 | 2048 | R3/S0/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| F_p0 | 8192 | R3/S0/P0/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| F_p1 | 2048 | R3/S0/P1/C0 | no_fault | EXECUTED | NOT_APPLICABLE | 1047 | 2048 | original_entry_time_tth | P1 did not exercise positive applicability/attempt/prepare/validate/commit audit counts; configuration is NOT_APPLICABLE to the bounded-local PIBT depth comparison / P1 did not execute a successful multi-bag atomic batch; configuration is NOT_APPLICABLE to the bounded-local PIBT depth comparison |
| F_p2 | 2048 | R3/S0/P2/C0 | no_fault | EXECUTED | NOT_APPLICABLE | 1047 | 2048 | original_entry_time_tth | P2 did not exercise positive applicability/attempt/prepare/validate/commit audit counts; configuration is NOT_APPLICABLE to the bounded-local PIBT depth comparison / P2 did not execute a successful multi-bag atomic batch; configuration is NOT_APPLICABLE to the bounded-local PIBT depth comparison |
| F_p3 | 2048 | R3/S0/P3/C0 | no_fault | EXECUTED | NOT_APPLICABLE | 1047 | 2048 | original_entry_time_tth | P3 did not exercise positive applicability/attempt/prepare/validate/commit audit counts; configuration is NOT_APPLICABLE to the bounded-local PIBT depth comparison / P3 did not execute a successful multi-bag atomic batch; configuration is NOT_APPLICABLE to the bounded-local PIBT depth comparison |
| F_p4 | 2048 | R3/S0/P4/C0 | no_fault | EXECUTED | NOT_APPLICABLE | 1047 | 2048 | original_entry_time_tth | P4 did not exercise positive applicability/attempt/prepare/validate/commit audit counts; configuration is NOT_APPLICABLE to the bounded-local PIBT depth comparison / P4 did not execute a successful multi-bag atomic batch; configuration is NOT_APPLICABLE to the bounded-local PIBT depth comparison |

## Claim boundary

- P0-P4 share local_queue_capacity=32 as one explicit sensitivity value; this is not a physical-capacity claim.
- P1-P4 require positive applicability, attempt, prepare, and validate counts; all published coordination counters must be present and non-negative, while zero handoffs alone remain valid.
- An unlimited-capacity P1-P4 execution is NOT_APPLICABLE, never PASS.
- The real-map motif suite remains the evidence for actual inheritance, backtracking, cycle guards, and rollback behavior.
