# Feng/common executor static-free-flow bridge audit

## Outcome

The route input is aligned: all **1510/1510** reachable ordered
map2 OD pairs selected the same full node sequence, and their edge-only travel
times agree to at most **2.84217094304e-14 s**.  All 1510 common
OD probes had zero source queue, zero local wait, and zero retry, so these are
genuine non-overlapping single-bag controls.

This does **not** make the executors mechanically equivalent.  The Feng control
uses a 0.2 s position lattice and the recovered legacy node-through service;
the common executor retains continuous event time, node service, calendars,
immediate source arbitration, and coordination machinery.  The single-bag mechanical gap
(common minus Feng) is [-43.000000, 1.000000] s
(mean -13.444179 s),
which is recorded rather than subtracted from any G31--DH result.

## Static OD control

- Map: `legacy/jichang_origin_readonly/map2.txt` (55f578cb4b8fcc61f5b13963fcb8546aca91e517ea6f8ff4a7361670f1b03f8f)
- Reachable ordered OD pairs (excluding start=goal): 1510
- Shared score: `edge_length / 2.5 + H_FF(next, goal)`
- Shared tie-break: minimum next-node ID; recursively this is the lexicographically
  minimum full node sequence. Origin score ties observed: 0.
- Feng edge-lattice quantization bias: 0--0 s
  (mean 0 s). Map2 edge times are exact 0.2 s multiples,
  so this specific map has zero quantization bias; the audit did not assume it.
- Common binary: `C:\PROGRAMING\czr005\.cie_native_dh_worktree\build_cie_revision\python\Release\czr005_cpp.cp311-win_amd64.pyd` (085a87615d5cd9a38fa3c7e5a26249ea99593d1a9277d064dd5a309a03452aca)

The common OD execution is the existing `P0D0` configuration: H_FF selected,
Q/I/corridor-wait/service-wait score terms masked off. Releases are 1000 s apart,
larger than every observed single-bag completion time, solely to keep each OD
probe empty-network. No route or timing result was used to tune the control.

## Original map2 1x full population

| executor | completed raw | completed segments | min | mean | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Feng static | 28506/28506 | 43603/43603 | 210.200 | 250.236 | 315.550 | 381.200 | 516.400 |
| Common H_FF / dynamic off | 28506/28506 | 43603/43603 | 188.001 | 239.822 | 349.060 | 422.032 | 577.807 |

Both rows use the original 28,506-raw / 43,603-segment canonical workload and
admission-to-goal-arrival raw-bag timing, excluding EBS scheduled storage wait.
The common row still contains its executor release/injection and coordination semantics (including
strict descent, FIFO merge grants, event hotpath and bounded-local feasibility),
even though the four dynamic route-score terms are off. Therefore the full-run
difference is a package-level executor/mechanics contrast, not a route-only
effect and not an estimate to subtract from the G31--DH gap.

## Goal completion boundary

Feng completes after the final-edge arrival and any positive goal service on a
discrete tick.  The common cell completes on physical goal arrival and does not
execute goal-node service. Both execute source/intermediate service, but their
service and time-discretization mechanics differ. The OD table exposes both
executors' node-service seconds separately. The Feng single-bag THT is measured
from first edge admission, so its post-admission field excludes source service
and includes intermediate/goal service; edge travel remains identical.

## Artifacts

- `outputs\tables\feng_common_executor_bridge.csv`: every OD plus the two 1x population rows
- `outputs\runtime\feng_common_executor_bridge\feng_static_od.csv`: Java position-lattice OD output
- `outputs\runtime\feng_common_executor_bridge\common_static_od.csv`: native common-executor OD output
- `outputs\runtime\feng_common_executor_bridge\common_static_od_metadata.json`: binary, H_FF and empty-network identity
- `outputs\runtime\feng_common_executor_bridge\feng_static_map2_1x\summary.csv`: Feng static 1x summary
- `outputs\runtime\feng_common_executor_bridge\common_static_map2_1x.json`: common P0D0 canonical 1x result
