# G4IRSF18 G17 39D research-bridge diagnostic

Status: **`BLOCKED_ABI_MISSING_SOURCE_POLICY_TAIL`**.

This is a bounded research diagnosis, not a production authorization or a
claim of G4IRSF18 60D/native parity. The published G17 gate remains unchanged:
`authorized=false` and `runtime_closed_loop_authorized=false`.

## Exact command

```powershell
C:\Users\38908\.conda\envs\czr005\python.exe scripts\eval\run_g4irsf18_g17_bridge_diagnostic.py --binary C:\PROGRAMING\czr005\build_g17_agent_pybind_latest\python\czr005_cpp.cp311-win_amd64.pyd --research-closed-loop
```

Structured output:
`outputs/tables/g4irsf18_g17_bridge_diagnostic.json`.

## Native interface result

The requested binary's `g4irsf11_event_runtime_from_records` signature ends at
`g4irsf17_source_wait_trace_limit`. It does not expose the three append-only
source-policy arguments:

1. `g4irsf17_source_policy_mode`;
2. `g4irsf17_source_policy_artifact`;
3. `g4irsf17_source_policy_trace_limit`.

Passing either the published shadow bundle or an in-memory research-only gate
copy therefore fails at the binding boundary before the simulation starts.
Dynamic proposal, selector-pass and action-mutation counts are **unavailable**,
not measured zeros. The research closed-loop request was recorded but not
executed.

The available source-wait trace is also insufficient as a substitute. Its
rows contain blocker interval identity/timing and affected-bag counts, but not
the exact 39D candidate/context observation. Reconstructing 39D values from
those 18 fields would invent missing live state and would not establish native
parity.

## Real-prefix control evidence

Both protected prefixes ran through the explicitly requested binary with the
frozen E4/F2 controls and source-wait telemetry enabled.

| Prefix segments | Complete tasks | Events | Mean TTH s | P95 TTH s | P99 TTH s | Mean source wait s | Safety |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 144 | 72/72 | 14,969 | 10,212.422339 | 11,436.123604 | 11,543.198445 | 1.274306 | PASS |
| 512 | 256/256 | 54,469 | 8,816.721934 | 11,183.227207 | 11,755.365823 | 3.126953 | PASS |

TTH uses the frozen `original_entry_time_tth` denominator. Both runs completed
every segment with zero failed segments, reservation conflicts, physical-fault
edge-entry violations, full A* calls, global reservation scans and unresolved
deadlocks, and stayed below the event cap.

## Gate reading and claim boundary

The published artifact's offline calibration check passes
(`0.061493 <= 0.08`), but the frozen support gate fails, validation activation
count is zero, and both production authorization booleans are false. Even a
research-only relaxation cannot be tested on the requested binary because the
ABI cannot accept the model or gate.

The narrow repair is to rebuild commit `1355dd6` with its already-present G17
source-policy binding, or use a validated G18 binary that preserves that tail.
Only then should shadow proposals be counted; a fixed-144 ephemeral closed loop
may follow if shadow/control safety passes. This old binary must not be cited as
learned normal-flow action evidence.
