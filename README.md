# czr005

JunctionShield-MARL for airport Individual Carrier System baggage routing.

This repository starts from the legacy Java/Eclipse ICS simulator and builds a faithful headless research stack:

```text
legacy Java reference
  -> Python reference parser/simulator
  -> C++ high-performance core
  -> Python learning environment
  -> shielded decentralized policies
```

Current scope:

- Phase0/Phase1 legacy source fixation, map/task parsing, Python reference simulator, C++ reference event-simulator smoke parity, `czr005.cpp_backend` build-tree loading, and explicit Java-compatible parsing for the ragged `example1/map.txt` heuristic fixture with Python/C++ A* parity.
- Java/Python/C++ A* planner performance gate: headless legacy Java `Astar.research` benchmark now runs without modifying the read-only Java project; Release C++ pybind A* matches Java paths and is faster on the recorded `map2/inputdata` task-window benchmark.
- Java/C++ legacy scheduler-window gates: external headless harnesses call read-only Java `ICS_PathFinding`, while native C++ mirrors task arrival, active-route advancement, constraint rebuilds, unfinished retries, scheduled fault/repair propagation including first-edge active-route fault removal, deterministic probability-extreme fault/repair generation, and A* planning on the same `map2/inputdata` windows; planned route multiset parity passes and Release C++ is faster on the recorded no-fault, deterministic fault/repair, and probability-extreme benchmarks.
- Phase2 non-learning baselines: A*, reservation/SIPP, queue-aware shortest path, rolling-horizon SIPP, route-discarding periodic SIPP replanning with static/repair-window faults, explicit buffer-capacity and merge-group shield checks, PIBT-style shield with bounded recursive handoff, active-bag PIBT replay parity, and active-bag/replan-cost diagnostics.
- Phase8 native C++ event replay with Python/C++ parity over persisted synthetic schedules and real legacy `map2/inputdata` windows, including repair windows plus explicit buffer-capacity and merge-group configurations where configured.
- Phase9 early runtime scaling, matched baseline-comparison, heldout-like synthetic matched diagnostics, dense active-bag PIBT stress sweeps, randomized-topology/task-source PIBT stress and all-family matched sweeps, repeated matched-family timing with local hardware metadata/95% CIs, and unified evidence diagnostics compare Python/native C++ throughput while surfacing existing Phase2/Phase5/Phase8 baseline evidence in one table.
- G2 learning-gap autopsy over the Phase9 matched real windows: `outputs/reports/g2_learning_gap_autopsy.md` localizes the current EdgeScore gap (`97/144` vs SIPP `144/144`) into failed task inventories, first-divergence rows, policy-vs-SIPP decision slices, failure motifs, and a heatmap. This is diagnostic evidence for the next teacher/oracle stage, not a learning-success claim.
- G3 oracle upper-bound diagnosis: `outputs/reports/g3_oracle_upper_bound_report.md` replays SIPP teacher-next, SIPP-rank, and K-step lookahead oracles under the same event candidate set and hard shield. Teacher next-hop candidate recall is `1.000`, but safe-mask recall is only `0.319`; the best local oracle recovers `11/47` EdgeScore failures with zero post-shield conflicts, pointing next toward mask/shield/event-horizon audit plus targeted teacher data, not RL.
- G3c Legacy-A* teacher fidelity audit: `outputs/reports/g3c_legacy_astar_teacher_fidelity_report.md` converts Python legacy-compatible A* routes into per-junction labels while using existing Java/C++ legacy acceptance artifacts as verifier evidence. Legacy-A* next-hop candidate recall is `1.000` and safe-mask recall improves to `0.610` with zero post-shield conflicts, but replay plans only `78/144` tasks and leaves `614` blocked/unavailable slices, so the next step remains targeted G3b mask/shield/event-horizon audit before broad G4A teacher scaling.
- G3d Legacy-A* wait/horizon audit: `outputs/reports/g3d_legacy_teacher_wait_horizon_audit_report.md` replays baseline, fixed-hold, earliest-safe jump, reroute-from-current, capacity/merge diagnostic ablation, and hybrid repair variants. The best primary Legacy wait/reroute replay reaches only `94/144` planned with zero conflicts, below the `115/144` G4A gate; edge-capacity ablation reaches `125/144` but creates `491` real-constraint conflicts, so this remains a diagnostic pass and training/G4A scaling stay paused.
- G3e event-semantics repair: `outputs/reports/g3e_event_semantics_repair_report.md` fixes downstream repair-window reachability so temporary repairable faults no longer make upstream waiting nodes look permanently unreachable, while permanent faults and currently faulted candidate edges remain blocked. The matched-window gate still fails (`94/144` best primary replay), confirming the next blocker is edge-capacity-aware teacher/scheduler timing rather than a safe-to-bypass mask.
- G3f edge-capacity-aware Legacy scheduler audit: `outputs/reports/g3f_edge_capacity_legacy_scheduler_report.md` separates paper-faithful Legacy-A* route intent from runtime-safe executable labels, adds edge-release wait, FIFO queue, wait-budget reroute, route-intent-only, and hybrid executable variants, and emits edge block/release/queue ledgers plus route/executable JSONL samples. Best pure Legacy executable replay is `96/144` with zero real conflicts, branch executable coverage `0.967`, route-intent coverage `144/144`, and unresolved edge-capacity share `0.054`; this is a diagnostic pass because the planned-count gate remains below `115/144`, so G4A/training stay paused.
- G3g Legacy scheduler semantics alignment: `outputs/reports/g3g_legacy_scheduler_semantics_alignment_report.md` compares Legacy node-window full-route scheduling with strict G3f local executable replay, while keeping non-CIE runtime references out of the teacher role. All `29/29` G3f unresolved capacity cases are current-node hold-capacity failures; Legacy node-window full-route reaches `127/144` but creates `458` real edge/merge conflicts. This confirms a scheduler-scope/backpressure semantics gap, not a green light for G4A/training.
- G3h CIE backpressure / pre-reservation audit: `outputs/reports/g3h_backpressure_pre_reservation_audit_report.md` keeps the original CIE/Legacy A* project as the teacher source and tests whether its route intent can be wrapped with upstream waiting before a full edge. CIE same-edge upstream waits project to `117/144`, CIE plus CIE-sourced upstream reroute projects to `119/144`, and raw CIE still has `458` real edge/merge conflicts if executed blindly; this is a diagnostic pass that requires G3i closed-loop replay before any G4A/training.
- G3i CIE/A* path-constrained SIPP integration: `outputs/reports/g3i_cie_sipp_integration_report.md` adds `LegacyRouteSIPPPlanner` / `LegacyRouteSIPPBaseline`, where original CIE/Legacy A* chooses the fixed route and the wrapper only retimes that path. G3j supersedes the initial edge-capacity interpretation below.
- G3j unverified edge-capacity removal: `outputs/reports/g3j_unverified_edge_capacity_audit_report.md` corrects the primary scope to original CIE/A* route intent plus Java-style node time windows and fault edges only. `edge_capacity=1` and merge-group capacity are now optional diagnostics, not teacher-label or gate constraints. The corrected primary real `map2/inputdata` replay reaches `127/144`, has `0` original node-window conflicts, and preserves A* paths for `127/127` planned routes; strict edge-capacity overlaps (`433`) are reported only as diagnostics.
- Learning experiments are still smoke/prototype scope, not final paper-grade RL results.
- Legacy Java files are read-only reference material.

## Quick Start

```powershell
conda env create -f environment.yml
conda activate czr005
python scripts/convert_legacy/convert_map2.py
python scripts/convert_legacy/convert_inputdata.py
python -m pytest
```

## Legacy Source

The Java reference project is expected at:

```text
legacy/jichang_origin_readonly
```

It is copied from `jichang_origin` and should not be modified in this repository.
