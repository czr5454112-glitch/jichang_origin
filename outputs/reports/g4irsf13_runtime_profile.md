# G4IRSF13 Runtime Profile

Status: `PROFILE_COMPLETE_NO_OPTIMIZATION_APPLIED`

Population: 43603 protected segments; deterministic repeats: 5.

- mean Python end-to-end wall: 10.673408s
- mean native event-runtime wall: 10.077575s
- mean pybind/payload residual wall: 0.595833s
- mean native decision latency p50/p95/p99: 8.000000/15.200000/19.180000 us
- process peak working set upper bound: 494280704 bytes
- repeat algorithm/binary equivalence: True

This stage profiles F2 as future-scaling preparation. Runtime speed does not explain or close the baggage TTH gap, and this study applies no algorithm or safety change.

Native aggregate and shared decision-latency timers are measured. The following requested subsystems currently expose counters but no independent native timer: event_heap, local_calendar, pibt_prepare_validate, pibt_owner_map, first_edge_credit_lifecycle. They remain explicitly counter-only; no fabricated percentage or optimization claim is made.

Trace serialization and file I/O are excluded by the summary-only, preloaded-input profile and are therefore `NOT_MEASURED`, not assumed free. Any future optimization must first add an isolated native timer and then prove deterministic result, TTH, counter, and safety equivalence.

## G4J / Phase K / Phase L unlock decision

| Gate | Pass | Canonical source field |
|---|---:|---|
| `strict_v2_win` | `false` | `original_scale_joint_candidate.strict_win_vs_v2_safe` |
| `v3_contribution` | `false` | `original_scale_joint_candidate.v3_contribution_proven` |
| `fault_discriminating` | `true` | `fault_control.status` |
| `numeric_demand_calibration` | `false` | `demand_calibration.phase_l_gates.numeric_real_demand_calibration_complete` |
| `original_task_generation_audit` | `true` | `demand_calibration.phase_l_gates.original_task_generation_audit_pass` |

- G4J: `CLOSED`
- Phase K: `UNKNOWN/CLOSED`
- Phase L: `NOT_RUN`
- scale execution: `NOT_RUN` (count=0)

The five gates are conjunctive. Two supporting gates pass (fault discrimination and original-task generation audit), but the strict-v2, V3-contribution, and numeric-demand-calibration gates are false. The validator therefore fails closed: G4J stays closed, K remains unknown/closed, L is not run, and no scale workload is executed.
