# G4IRSF12 Stable-Load Fault Recovery

Status: `PROTOCOL_READY_NO_NEW_EXECUTION`.

Every unexecuted case is retained as `NOT_RUN` / `PENDING`. No planned
row is treated as PASS, and incomplete survivor timing is excluded from
comparison.

## Evidence ledger

| Case | Size | R/S/P/C | Fault | Execution | Gate | Complete bags | Segments | Denominator | Blocker |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| H_stable_no_fault | 2048 | R3/S0/P2/C6 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires a stable no-fault real-input candidate before fault injection |
| H_stable_no_fault | 8192 | R3/S0/P2/C6 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| H_stable_no_fault | 43603 | R3/S0/P2/C6 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted 8192 evidence and explicit full-run authorization |
| H_immediate | 2048 | R3/S0/P2/C6 | single_immediate | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires a stable no-fault real-input candidate before fault injection |
| H_immediate | 8192 | R3/S0/P2/C6 | single_immediate | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| H_immediate | 43603 | R3/S0/P2/C6 | single_immediate | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted 8192 evidence and explicit full-run authorization |
| H_delayed_30s | 2048 | R3/S0/P2/C6 | single_delayed_30s | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires a stable no-fault real-input candidate before fault injection |
| H_delayed_30s | 8192 | R3/S0/P2/C6 | single_delayed_30s | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| H_delayed_30s | 43603 | R3/S0/P2/C6 | single_delayed_30s | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted 8192 evidence and explicit full-run authorization |
| H_notification_drop | 2048 | R3/S0/P2/C6 | sensor_loss | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires a stable no-fault real-input candidate before fault injection |
| H_notification_drop | 8192 | R3/S0/P2/C6 | sensor_loss | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| H_notification_drop | 43603 | R3/S0/P2/C6 | sensor_loss | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted 8192 evidence and explicit full-run authorization |
| H_fault_policy_off | 2048 | R3/S0/P2/C6 | fault_policy_off | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires a stable no-fault real-input candidate before fault injection |
| H_fault_policy_off | 8192 | R3/S0/P2/C6 | fault_policy_off | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted prior tier and explicit 8192 authorization |
| H_fault_policy_off | 43603 | R3/S0/P2/C6 | fault_policy_off | NOT_RUN | PENDING |  |  | original_entry_time_tth | requires accepted 8192 evidence and explicit full-run authorization |

## Claim boundary

- Fault injection starts only after a no-fault candidate is stable on the same real-input window.
- Physical interlock and unsafe-entry accounting are never disabled.
- A recovery PASS requires affected-bag completion plus true runtime availability for finite non-negative recovery seconds and a finite non-positive post-repair backlog slope.
