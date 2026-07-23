# G4IRSF11 Local-Control System A/B

Generated: `2026-07-23`.

A/B rows change one declared local controller component. Two-hop state is diagnostic-only; reservations remain one step.

Execution status counts: `{"EXECUTED": 9}`.

| Case | Mode | Scale | Exec | Safe | Queue | Service | Capacity | p99 s | End backlog | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ablation_aging_full | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 249774.42493322946 | 68158 |  |
| ablation_backpressure_off | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 230103.8664625156 | 68026 |  |
| ablation_deadlock_escape_off | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 251858.96569552473 | 68158 |  |
| ablation_diagnostic_one_hop | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 249774.42493322946 | 68158 |  |
| ablation_diagnostic_two_hop | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 249774.42493322946 | 68158 |  |
| ablation_pibt_lite_off | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 217933.9496979636 | 68925 |  |
| ablation_queue_deadline | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 259694.53336665558 | 68145 |  |
| ablation_queue_fifo | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 247760.71651696347 | 68347 |  |
| ablation_source_admission_off | empirical_interarrival_jitter | 2.5 | EXECUTED | True | False | False | False | 262007.2719377066 | 68145 |  |
