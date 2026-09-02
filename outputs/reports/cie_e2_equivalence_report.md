# CIE E2 strict physical-equivalence and compute specialty

Status: `COMPLETE_STRICT_PHYSICAL_EQUIVALENCE`.

| Map | Pair status | Physical equivalence | E0 events | E2 events | Event reduction | E0 wall s | E2 wall s |
|---|---|---:|---:|---:|---:|---:|---:|
| map2 | STRICT_PHYSICAL_EQUIVALENCE_PASS | True | 4752689 | 3997648 | 0.15886606508441853 | 39.741719000041485 | 38.50778639991768 |
| nanning | STRICT_PHYSICAL_EQUIVALENCE_PASS | True | 8645838 | 7087605 | 0.18022926175577197 | 85.12288339994848 | 76.90544579993002 |

## Physical-causal event count audit

Each count is shown as `E0 / E2`.

| Map | Release | Arrive | Service complete | Edge enter | Edge exit | Fault | Repair | Total | Equality gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| map2 | 43603 / 43603 | 336638 / 336638 | 336638 / 336638 | 336638 / 336638 | 336638 / 336638 | 0 / 0 | 0 / 0 | 1390155 / 1390155 | True |
| nanning | 43603 / 43603 | 588936 / 588936 | 588936 / 588936 | 588936 / 588936 | 588936 / 588936 | 0 / 0 | 0 / 0 | 2399347 / 2399347 | True |

The physical-causal total is the sum of release, arrival, service-complete, edge-enter, edge-exit, fault and repair events. Equality of these components is a strict paired diagnostic gate.

## Beacon, stale-event and wakeup telemetry

Each count is shown as `E0 / E2`.

| Map | Redundant beacon suppressed | Same-state beacon suppressed | Stale arbitration | Merge stale arbitration | Merge stale wakeup | Stale total | Wakeup scheduled | Wakeup coalesced | Duplicate wakeup prevented |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| map2 | 0 / 563287 | 0 / 191754 | 0 / 0 | 9465 / 9465 | 9465 / 9465 | 18930 / 18930 | 163057 / 163057 | 121611 / 76152 | 121611 / 76152 |
| nanning | 0 / 925122 | 0 / 633111 | 0 / 0 | 26690 / 26690 | 26690 / 26690 | 53380 / 53380 | 323045 / 323045 | 283454 / 185585 | 283454 / 185585 |

E0 performs no G20 beacon suppression, so both E0 suppression counts are definitionally zero; the native binding omits those counters under E0. Stale and wakeup counts are paired compute diagnostics and are not physical-equivalence gates.

Strict equivalence requires identical per-segment terminal states, completion/admission/release times (absolute tolerance 1e-9 s), and the complete untruncated move/hold physical sequence.

`event_queue_peak` is `N/M`: the current public executor response does not expose that quantity. Junction/source queue peaks are not used as substitutes. Wall, CPU, and process-lifetime peak RSS are descriptive single-run values under complete-trace instrumentation, not variance-controlled production speed claims.

This specialty compares E0 and E2 only within the same map, current G31 coordination/release protocol, and 1x workload. It does not support a cross-protocol ranking or capacity claim.
