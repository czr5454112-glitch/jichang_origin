# G4IRSF17 native fault campaign

Faults are event-runtime availability overlays on the unchanged real map. Uninformative exposure, missing recovery telemetry, timeout, and OOM remain explicit.

Protocol status: **`AMENDED`**.
Original 1x matrix complete: **True**; original 4x matrix complete: **False**.
4x fault advantage: **`NOT_ESTIMABLE`**.
Amended 4x rows are terminal for campaign accounting, but are not executed, evaluable, passed, or failed fault treatments. No synthetic job-result JSON is created.

| Candidate | Load | Scenario | Status | Execution | Evaluable | Affected | Completion | Capacity segments | Recovery s | Hard gate |
|---|---|---|---|---|---|---|---|---|---|---|
| E4_OFF | 1x | no_fault | COMPLETE | EXECUTED | True | 0 | 1.0000 | — | — | True |
| E4_OFF | 1x | noncritical_edge | COMPLETE | EXECUTED | True | 23 | 1.0000 | — | 49.5020 | True |
| E4_OFF | 1x | critical_bottleneck | COMPLETE | EXECUTED | True | 1 | 1.0000 | — | 46.4010 | True |
| E4_OFF | 1x | merge_incoming_edge | COMPLETE | EXECUTED | True | 22 | 1.0000 | — | 75.5020 | True |
| E4_OFF | 1x | source_first_edge | COMPLETE | EXECUTED | True | 1 | 1.0000 | — | 201.0010 | True |
| E4_OFF | 1x | ebs_outgoing_edge | COMPLETE | EXECUTED | True | 0 | 1.0000 | — | — | False |
| E4_OFF | 1x | dual_disjoint | COMPLETE | EXECUTED | True | 2 | 1.0000 | — | 89.3020 | True |
| E4_OFF | 1x | dual_interacting | COMPLETE | EXECUTED | True | 2 | 1.0000 | — | 201.0010 | True |
| E4_OFF | 1x | delayed_beacon | COMPLETE | EXECUTED | True | 22 | 1.0000 | — | 75.5020 | True |
| E4_OFF | 1x | dropped_intermediate_beacon | COMPLETE | EXECUTED | True | 22 | 1.0000 | — | 75.5020 | True |
| E4_OFF | 1x | repair_reopen | COMPLETE | EXECUTED | True | 1 | 1.0000 | — | 46.4010 | True |
| E4_OFF | 4x | no_fault | CAPACITY_CENSORED_BY_EQUIVALENT_CONTROL | EVIDENCE_REUSED | False | — | — | 10093/174412 | — | None |
| E4_OFF | 4x | noncritical_edge | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | critical_bottleneck | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | merge_incoming_edge | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | source_first_edge | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | ebs_outgoing_edge | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | dual_disjoint | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | dual_interacting | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | delayed_beacon | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | dropped_intermediate_beacon | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |
| E4_OFF | 4x | repair_reopen | NOT_RUN_CONTROL_CENSORED | NOT_RUN | False | — | — | — | — | None |

Track status: **`TERMINAL_WITH_CAPACITY_CENSORING`**.
Reused capacity evidence: `scale__e4_off__4x` reached 20,000,000 events with 10,093/174,412 segments completed.
