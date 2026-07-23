# G4IRSF12 Pressure and Credit Design

Status: `PROTOCOL_READY_NO_NEW_EXECUTION`.

Every unexecuted case is retained as `NOT_RUN` / `PENDING`. No planned
row is treated as PASS, and incomplete survivor timing is excluded from
comparison.

## Evidence ledger

| Case | Size | R/S/P/C | Fault | Execution | Gate | Complete bags | Segments | Denominator | Blocker |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| G_c0 | 2048 | R3/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| G_c0 | 8192 | R3/S0/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| G_c1 | 2048 | R3/S0/P0/C1 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| G_c1 | 8192 | R3/S0/P0/C1 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| G_c2 | 2048 | R3/S0/P0/C2 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| G_c2 | 8192 | R3/S0/P0/C2 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| G_c3 | 2048 | R3/S0/P0/C3 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| G_c3 | 8192 | R3/S0/P0/C3 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| G_c4 | 2048 | R3/S0/P0/C4 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| G_c4 | 8192 | R3/S0/P0/C4 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| G_c5 | 2048 | R3/S0/P0/C5 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| G_c5 | 8192 | R3/S0/P0/C5 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| G_c6 | 2048 | R3/S0/P2/C6 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | awaiting execution in frozen prefix order |
| G_c6 | 8192 | R3/S0/P2/C6 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |

## Claim boundary

- C0--C6 are separate A/B labels; absent executor capabilities remain PENDING.
- C0--C6 share local_queue_capacity=32, so pressure/credit/PIBT labels are not confounded by unlimited-versus-finite queues.
- Credit binds only the first selected edge and cannot create a future route.
- Differential pressure is an engineering local signal, not a throughput-optimality claim.
