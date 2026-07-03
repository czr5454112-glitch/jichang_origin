# G4I Runtime Speed Benchmark Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `b3d2296`
Contains G4H: `True`
Pushed to upstream at runtime: `True`

## Result

| System | Mean Seconds | CI95 | Planned | Full A* | Notes |
| --- | --- | --- | --- | --- | --- |
| python_model_plus_pibt_lite | 10.6607754 | 1.58386115 | 4449 | 0 | Python reference event loop over G4D teacher planned scope |
| cpp_model_plus_pibt_lite | 0.50506883 | 0.10834637 | 4449 | 0 | C++ owns full no-A* episode replay; Python only invokes pybind once per repeat |
| verified_cie_retry_baseline_astar_proxy | 0.18993917 | 0.02331882 | 4449 | 15852 | Measured C++ static A* plan proxy scaled to original retry attempt count; this is a lower-bound proxy, not the Java GUI runtime |
| g4d_model_plus_cie_fallback_call_count |  |  | 4449 | 6786 | Existing call-count baseline retained for G4D/G4E; no new speed claim from this row. |
| g4e_model_plus_cie_fallback_call_count |  |  | 4449 | 6395 | Existing call-count baseline retained for G4D/G4E; no new speed claim from this row. |

The verified CIE row is a measured static A* proxy scaled to the original retry-attempt count; it is a local lower-bound proxy, not a Java GUI runtime claim.
