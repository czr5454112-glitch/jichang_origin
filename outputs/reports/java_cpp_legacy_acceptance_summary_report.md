# Java / C++ Legacy Acceptance Summary

Date: 2026-06-24

## Scope

This summary is a read-only audit over the generated Java/C++ benchmark tables. It verifies that every recorded legacy-performance gate has Java/C++ functional parity and that Release C++ throughput is not below the read-only legacy Java baseline.

The legacy Java project remains reference-only; these gates use external harnesses and native C++ ports.

## Gates

| Gate | Scope | C++/Java speedup | Summary | Route/path parity | Performance |
|---|---|---:|---|---|---|
| astar_core | legacy Java Astar.research vs Python reference and C++ pybind A* on 8000 map2/inputdata cases | 1.736x | PASS | PASS | PASS |
| legacy_no_fault_window | read-only Java ICS_PathFinding no-fault headless scheduler window vs native C++ | 48.661x | PASS | PASS | PASS |
| legacy_scheduled_fault_window | deterministic scheduled fault/repair, including first-edge active-route fault removal | 49.392x | PASS | PASS | PASS |
| legacy_probability_extreme_window | deterministic probability-extreme Tasks.generate_tasks branches, fault_probability=1.0 repair_probability=0.0 | 38.574x | PASS | PASS | PASS |

CSV: `outputs/tables/java_cpp_legacy_acceptance_summary.csv`

## Acceptance Status

- all recorded Java/C++ legacy gates pass: PASS
- minimum C++/Java speedup across recorded gates: `1.736x`
- legacy Java source modification: not required by these gates

## Boundary

The acceptance evidence covers the computational core and headless legacy scheduler paths used by the project: A*, no-fault scheduling, deterministic fault/repair including active-route first-edge removal, and deterministic probability-extreme task-generation branches. Intermediate random probabilities are not used as a parity gate because the read-only Java project does not expose an injectable random seed. Swing repaint/sleep timing is GUI behavior rather than the Python/C++ compute runtime target.
