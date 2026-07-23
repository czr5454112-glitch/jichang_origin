# G4IRSF12 Resource Semantics Runtime Plan

Status: `PROTOCOL_READY_NO_NEW_EXECUTION`.

Every unexecuted case is retained as `NOT_RUN` / `PENDING`. No planned
row is treated as PASS, and incomplete survivor timing is excluded from
comparison.

## Evidence ledger

| Case | Size | R/S/P/C | Fault | Execution | Gate | Complete bags | Segments | Denominator | Blocker |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| C_r0 | 144 | R0/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r0 | 512 | R0/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r0 | 2048 | R0/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r0 | 8192 | R0/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| C_r1 | 144 | R1/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r1 | 512 | R1/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r1 | 2048 | R1/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r1 | 8192 | R1/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| C_r2 | 144 | R2/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r2 | 512 | R2/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r2 | 2048 | R2/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r2 | 8192 | R2/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| C_r3 | 144 | R3/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r3 | 512 | R3/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r3 | 2048 | R3/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r3 | 8192 | R3/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| C_r4 | 144 | R4/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r4 | 512 | R4/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r4 | 2048 | R4/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| C_r4 | 8192 | R4/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |

## Claim boundary

- This runtime-plan ledger does not overwrite the committed static resource-semantics audit.
- R0-R4 first run at 144/512/2048; only two reviewed resources may be selected for 8192.
- Unknown physical headway and queue capacity remain sensitivity-only.
