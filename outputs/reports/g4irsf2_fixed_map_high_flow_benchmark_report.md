# G4IRSF2 Fixed-Map High-Flow Benchmark Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `dafc6e0`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample

## Result

| Flow | Tasks | No-A* Planned | Conflicts | Full A* | No-A* s | A* Proxy s | Ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4096 | 4096 | 0 | 0 | 1.5596758997999132 | 0.0285712 | 0.018318677619924322 |
| 2 | 8192 | 8192 | 0 | 0 | 5.386308299843222 | 0.0619273 | 0.011497169592353728 |
| 4 | 16384 | 16384 | 0 | 0 | 18.70089460001327 | 0.1188078 | 0.006353054361362782 |
| 8 | 32768 | 32768 | 0 | 0 | 72.40894540003501 | 0.2458453 | 0.0033952338159572355 |

The A* baseline here is a same-task static A* lower-bound proxy, not a full Java GUI/CIE runtime. Negative speed results are retained.
