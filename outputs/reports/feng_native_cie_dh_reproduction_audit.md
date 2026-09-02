# Feng-native HCA / CIE-DH reproduction audit

Status: `FENG_NATIVE_HCA_REGRESSION_PASS`; `BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED`.

## Outcome

The recovered original Java HCA full run is an exact **frozen aggregate** regression match: 43,603/43,603 segments and 28,506/28,506 raw bags complete (100%), with processed-attempt min/mean/max of 3.133333/3.945169/5.950000 minutes. These equal the frozen 188.0/236.710166280783/357.0 second values exactly. This audit did not freeze or compare per-task release, route, or completion trace hashes, so it does not claim trace-exact path identity.

Feng-native CIE-DH is **not measured**. The recovered 15-source Java tree has no executable position-level state set needed to implement the historical rule. This audit does not relabel or substitute the modern common-executor adapted DH arm.

## Table 5.3 audit

| method | paper min/mean/max (min) | measured min/mean/max (min) | error min/mean/max | status |
|---|---:|---:|---:|---|
| FENG_NATIVE_HCA | 3.13/3.96/5.98 | 3.133333/3.945169/5.950000 | 0.106%/-0.375%/-0.502% | `FENG_NATIVE_HCA_REGRESSION_PASS` |
| FENG_NATIVE_CIE_DH_RECONSTRUCTION | 3.56/4.43/8.62 | — | — | `BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED` |

The paper values are validation references transcribed from the supplied action plan, not optimization targets. Error is emitted only for the measured HCA row.

## Source-semantic blocker

- Audited Java sources: `15`; aggregate SHA-256 `b0c7545abad1705eba9255527d39a864007bd576c9edbc9cb872a51e6acc9c25`.
- Executable-code match counts after stripping comments and string/character literals: `{"bti_state": 0, "ddi_state": 0, "dh_identifier": 0, "moving_state": 0, "point_two_second_literal": 0, "stopped_state": 0}`.
- Recovered call chain: `RUN.Main.run -> Tasks.generate_tasks -> ICS_PathFinding.ICS_path_finding -> Astar.research`. Every call-chain signature check passed: `True`.
- `ICS_GUI.cycle = 200` is consumed by `Thread.sleep(gui.getCycle())`; it is a GUI refresh interval in milliseconds, not DH's 0.2-second position/moving/stopped state transition.
- Conclusion: `The recovered sources contain the centralized epoch scheduler and A* reservation call chain, but no executable DH/moving/stopped/BTI/DDI/0.2-s state set. The 200 ms GUI refresh cycle is not a position-level DH update.`

## Provenance

- HCA summary SHA-256: `551186d4f7a05543fee4f6d10905b72f8b5df9fcd1d37aa5fdcd1b234b365f06`
- map2 SHA-256: `55f578cb4b8fcc61f5b13963fcb8546aca91e517ea6f8ff4a7361670f1b03f8f`
- inputdata SHA-256: `0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87`
- compiled classes: `27` files; aggregate SHA-256 `005f2cca4ede5f9d08668830a1d02f2b33a6d5e789ab29a2ef09fdded18c2b1f`

This is a read-only evidence audit: it did not compile or run Java, did not implement DH, and did not overwrite the earlier G4IRSF24 evidence namespace.
