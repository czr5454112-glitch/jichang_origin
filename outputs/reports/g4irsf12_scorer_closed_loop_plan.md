# G4IRSF12 Scorer Closed-Loop Plan

Status: `EXECUTED_EVIDENCE_AVAILABLE_NOT_AUTOMATIC_PROMOTION`.

Every unexecuted case is retained as `NOT_RUN` / `PENDING`. No planned
row is treated as PASS, and incomplete survivor timing is excluded from
comparison.

## Evidence ledger

| Case | Size | R/S/P/C | Fault | Execution | Gate | Complete bags | Segments | Denominator | Blocker |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| E_s0 | 2048 | R3/S0/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| E_s0 | 8192 | R3/S0/P0/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| E_s1 | 2048 | R3/S1/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| E_s1 | 8192 | R3/S1/P0/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| E_s2 | 2048 | R3/S2/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| E_s2 | 8192 | R3/S2/P0/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| E_s3 | 2048 | R3/S3/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| E_s3 | 8192 | R3/S3/P0/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| E_s4 | 2048 | R3/S4/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| E_s4 | 8192 | R3/S4/P0/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |

## Claim boundary

- This closed-loop plan does not overwrite the committed offline S0-S4 replay evidence.
- R3 is a planning anchor only; execution requires accepted C_R3 8192 evidence.
- Frozen G4E remains an out-of-distribution diagnostic and cannot be promoted as a new learned policy.
