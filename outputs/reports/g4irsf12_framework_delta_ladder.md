# G4IRSF12 Framework Delta Ladder

Status: `PARTIAL_WITH_NEGATIVE_RESULTS_RETAINED`.

Every unexecuted case is retained as `NOT_RUN` / `PENDING`. No planned
row is treated as PASS, and incomplete survivor timing is excluded from
comparison.

## Evidence ledger

| Case | Size | R/S/P/C | Fault | Execution | Gate | Complete bags | Segments | Denominator | Blocker |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| B_control_historical_hca_processed_segment_attempt_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | processed_segment_attempt_time_tth | historical/committed control only; no fresh execution |
| B_control_historical_hca_java_release_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | java_release_time_tth | historical/committed control only; no fresh execution |
| B_control_historical_hca_original_entry_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | original_entry_time_tth | historical/committed control only; no fresh execution |
| B_control_v2_safe_java_release_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | java_release_time_tth | historical/committed control only; no fresh execution |
| B_control_v2_safe_original_entry_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | original_entry_time_tth | historical/committed control only; no fresh execution |
| B2_old_order_one_step | 144 | R3/S1/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | OLD_SCHEDULING_ORDER_ONE_STEP_EXECUTOR_NOT_IMPLEMENTED |
| B2_old_order_one_step | 512 | R3/S1/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | OLD_SCHEDULING_ORDER_ONE_STEP_EXECUTOR_NOT_IMPLEMENTED |
| B2_old_order_one_step | 2048 | R3/S1/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | OLD_SCHEDULING_ORDER_ONE_STEP_EXECUTOR_NOT_IMPLEMENTED |
| B2_old_order_one_step | 8192 | R3/S1/P0/C0 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | OLD_SCHEDULING_ORDER_ONE_STEP_EXECUTOR_NOT_IMPLEMENTED |
| B3_event_java_window_frozen | 144 | R3/S1/P0/C0 | no_fault | EXECUTED | PASS | 72 | 144 | original_entry_time_tth |  |
| B3_event_java_window_frozen | 512 | R3/S1/P0/C0 | no_fault | EXECUTED | PASS | 256 | 512 | original_entry_time_tth |  |
| B3_event_java_window_frozen | 2048 | R3/S1/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| B3_event_java_window_frozen | 8192 | R3/S1/P0/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| B4_event_current_corridor_frozen | 144 | R0/S1/P0/C0 | no_fault | EXECUTED | PASS | 72 | 144 | original_entry_time_tth |  |
| B4_event_current_corridor_frozen | 512 | R0/S1/P0/C0 | no_fault | EXECUTED | PASS | 256 | 512 | original_entry_time_tth |  |
| B4_event_current_corridor_frozen | 2048 | R0/S1/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| B4_event_current_corridor_frozen | 8192 | R0/S1/P0/C0 | no_fault | PARTIAL | FAIL | 880 | 2892 | original_entry_time_tth | unresolved_deadlock_count=27, expected 0 / event_limit_reached=true / selected prefix did not complete; survivor metrics excluded |
| B5_event_corrected_handwritten | 144 | R3/S0/P0/C0 | no_fault | EXECUTED | PASS | 72 | 144 | original_entry_time_tth |  |
| B5_event_corrected_handwritten | 512 | R3/S0/P0/C0 | no_fault | EXECUTED | PASS | 256 | 512 | original_entry_time_tth |  |
| B5_event_corrected_handwritten | 2048 | R3/S0/P0/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| B5_event_corrected_handwritten | 8192 | R3/S0/P0/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 144 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 72 | 144 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 144 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 72 | 144 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 144 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 72 | 144 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 144 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 72 | 144 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 144 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 72 | 144 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 512 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 256 | 512 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 512 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 256 | 512 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 512 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 256 | 512 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 512 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 256 | 512 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 512 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 256 | 512 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 2048 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 2048 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 2048 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 2048 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 2048 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 1047 | 2048 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 8192 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 8192 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 8192 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 8192 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |
| B6_event_corrected_frozen_bounded_pibt | 8192 | R3/S1/P2/C0 | no_fault | EXECUTED | PASS | 4898 | 8192 | original_entry_time_tth |  |

## Claim boundary

- B0/B1 are parsed controls and are never disguised as fresh reruns.
- B2 remains NOT_RUN because the old scheduling-order one-step executor is not implemented.
- Each executable B3--B6 tier changes only its declared resource/scorer/PIBT controls.
- B3--B6 share local_queue_capacity=32 as sensitivity-only isolation, not as a physical-capacity claim.
- An 8,192 PASS authorizes only finalist review; it does not authorize full automatically.
