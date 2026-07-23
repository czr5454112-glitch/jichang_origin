# G4IRSF11 Temporal Fault/Repair

Generated: `2026-07-23`.

These are physical fault and repair windows with explicit notification delay/loss, not static edge-removal proxies. A null recovery time means NOT_RECOVERED_BY_RUN_END; it is explicit negative evidence and fails the recovery gate.

Execution status counts: `{"EXECUTED": 5}`.

| Case | Mode | Scale | Exec | Safe | Queue | Service | Capacity | p99 s | End backlog | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fault_fault_policy_off | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 255089.29480104835 | 68150 |  |
| fault_repeated_delayed_5s | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 255129.66362067912 | 68172 |  |
| fault_sensor_loss | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 254611.1152637878 | 68157 |  |
| fault_single_delayed_30s | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 252909.50993323184 | 68168 |  |
| fault_single_immediate | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 254611.1152637878 | 68157 |  |

| Case | Fault recovery | Recovered windows | Unrecovered windows | Recovery times s | Backlog before fault | Backlog at repair | Fault gate failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fault_fault_policy_off | False | 0 | 1 | [null] | [47837] | [52214] | window_0:affected_completion_pass,recovery_time_pass |
| fault_repeated_delayed_5s | False | 0 | 2 | [null,null] | [47837,52214] | [49865,55070] | window_0:affected_completion_pass,recovery_time_pass; window_1:affected_completion_pass,recovery_time_pass |
| fault_sensor_loss | False | 0 | 1 | [null] | [47837] | [52214] | window_0:affected_completion_pass,recovery_time_pass |
| fault_single_delayed_30s | False | 0 | 1 | [null] | [47837] | [52214] | window_0:affected_completion_pass,recovery_time_pass |
| fault_single_immediate | False | 0 | 1 | [null] | [47837] | [52214] | window_0:affected_completion_pass,recovery_time_pass |
