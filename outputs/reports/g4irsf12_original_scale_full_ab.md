# G4IRSF12 Original-Scale Full A/B

Status: `PARTIAL_WITH_NEGATIVE_RESULTS_RETAINED`.

Every unexecuted case is retained as `NOT_RUN` / `PENDING`. No planned
row is treated as PASS, and incomplete survivor timing is excluded from
comparison.

## Evidence ledger

| Case | Size | R/S/P/C | Fault | Execution | Gate | Complete bags | Segments | Denominator | Blocker |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| J_control_historical_hca_processed_segment_attempt_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | processed_segment_attempt_time_tth | historical/committed control only; no fresh execution |
| J_control_historical_hca_java_release_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | java_release_time_tth | historical/committed control only; no fresh execution |
| J_control_historical_hca_original_entry_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | original_entry_time_tth | historical/committed control only; no fresh execution |
| J_control_v2_safe_java_release_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | java_release_time_tth | historical/committed control only; no fresh execution |
| J_control_v2_safe_original_entry_time_tth | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 28506 | 43603 | original_entry_time_tth | historical/committed control only; no fresh execution |
| J_control_g4irsf11_negative | 43603 | historical | historical_control | NOT_RUN | NOT_APPLICABLE | 3114 | 12125 | original_entry_time_tth | historical/committed control only; no fresh execution |
| J_F3_reserved_no_v3 | 43603 | R3/S4/P2/C6 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | J_F3 is reserved until a trained and gated G4IRSF12 v3 artifact replaces the S4 queue-aware rule placeholder |
| J_control_resource_r0 | 43603 | R0/S0/P2/C6 | no_fault | NOT_RUN | PENDING |  |  | original_entry_time_tth | J R0 control lacks a fully matched 8192 preflight case |
| J_F1_best_rule_bounded_pibt | 43603 | R3/S0/P2/C6 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F1_best_rule_bounded_pibt | 43603 | R3/S0/P2/C6 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F1_best_rule_bounded_pibt | 43603 | R3/S0/P2/C6 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F1_best_rule_bounded_pibt | 43603 | R3/S0/P2/C6 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F1_best_rule_bounded_pibt | 43603 | R3/S0/P2/C6 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F2_frozen_scorer_bounded_pibt | 43603 | R3/S1/P2/C0 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F2_frozen_scorer_bounded_pibt | 43603 | R3/S1/P2/C0 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F2_frozen_scorer_bounded_pibt | 43603 | R3/S1/P2/C0 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F2_frozen_scorer_bounded_pibt | 43603 | R3/S1/P2/C0 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_F2_frozen_scorer_bounded_pibt | 43603 | R3/S1/P2/C0 | no_fault | EXECUTED | FAIL | 28506 | 43603 | original_entry_time_tth | original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_control_pibt_off | 43603 | R3/S0/P0/C5 | no_fault | PARTIAL | FAIL | 4189 | 7719 | original_entry_time_tth | unresolved_deadlock_count=32, expected 0 / event_limit_reached=true / selected prefix did not complete; survivor metrics excluded / J completed raw bags=4189, expected 28506 / original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_control_pibt_off | 43603 | R3/S0/P0/C5 | no_fault | PARTIAL | FAIL | 4189 | 7719 | original_entry_time_tth | unresolved_deadlock_count=32, expected 0 / event_limit_reached=true / selected prefix did not complete; survivor metrics excluded / J completed raw bags=4189, expected 28506 / original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_control_pibt_off | 43603 | R3/S0/P0/C5 | no_fault | PARTIAL | FAIL | 4189 | 7719 | original_entry_time_tth | unresolved_deadlock_count=32, expected 0 / event_limit_reached=true / selected prefix did not complete; survivor metrics excluded / J completed raw bags=4189, expected 28506 / original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_control_pibt_off | 43603 | R3/S0/P0/C5 | no_fault | PARTIAL | FAIL | 4189 | 7719 | original_entry_time_tth | unresolved_deadlock_count=32, expected 0 / event_limit_reached=true / selected prefix did not complete; survivor metrics excluded / J completed raw bags=4189, expected 28506 / original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |
| J_control_pibt_off | 43603 | R3/S0/P0/C5 | no_fault | PARTIAL | FAIL | 4189 | 7719 | original_entry_time_tth | unresolved_deadlock_count=32, expected 0 / event_limit_reached=true / selected prefix did not complete; survivor metrics excluded / J completed raw bags=4189, expected 28506 / original_entry_mean_minutes does not meet matched frozen v2-safe target <= 4.124305453 / original_entry_mean_minutes does not meet corrected historical HCA original-entry target <= 5.764936746 |

## Claim boundary

- Phase J is evaluated independently while G4J remains CLOSED; a Phase-J PASS does not open G4J.
- Only 28,506/28,506 bags and 43,603/43,603 segments can enter the primary comparison.
- Every finalist must meet both matched original-entry targets: frozen v2-safe 4.124305453 min and corrected historical HCA 5.764936746 min.
- The 3.967122711 min processed-attempt value is shown only as a non-comparable warning.
- Historical HCA* remains parsed engineering evidence, not a same-machine rerun.
