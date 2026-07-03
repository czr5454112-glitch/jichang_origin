# G4IRSF3 Fault-Aware Upstream Avoidance Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `209f895`
governance_doc: docs/czr005_project_governance.md
topology_changed: false
data_generation_rule_source: distribution_preserving_resample
runtime_full_cie_astar_fallback: false

## Finding

G4IRSF2 static 18->22 failures preserved: `1150` out of `4096`.
Repair-window failures preserved from G4IRSF2: `32`.

The repeated paths show the problem happens before node 18. Once a bag reaches 18 while 18->22 is broken, node 18 has no valid outgoing edge. The local fix has to happen upstream, for example at 16 or 19, and sometimes at the source if the first corridor has no safe branch.

## Shadow Variant Best Case

| Variant | Recovered | Held | Remaining | Promoted? |
| --- | --- | --- | --- | --- |
| shadow_dead_end_depth2_soft_penalty | 0 | 0 | 1150 | False |

The improvement is shadow-only: it uses only local static topology and the current fault edge, with no teacher path and no future schedule, but it is not wired into the promoted C++ runtime in this step.
