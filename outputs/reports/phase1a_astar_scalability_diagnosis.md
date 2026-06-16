# Phase1a A* Scalability Diagnosis

Date: 2026-06-16

## Scope

This is a planner-only scalability diagnostic over the real expanded task stream. It reuses each task leg's `(start, goal)` pair and does not model reservations, active queues, faults, or event-simulation feedback.

- map: `legacy/jichang_origin_readonly/map2.txt`
- task stream: `data/processed/tasks/inputdata.jsonl`
- base count: 500
- scales: [1, 2, 4, 8, 16]
- table: `outputs/tables/phase1a_astar_scalability.csv`
- figure: `outputs/figures/phase1a_runtime_vs_active_bags.png`
- figure status: generated

## Result

Checksum parity across Python and C++ planner runs: PASS

At the largest smoke size (8000 task-leg plans):

- Python reference: 1.837983 seconds, 4352.60 plans/s
- C++ pybind core: 1.516141 seconds, 5276.55 plans/s
- C++ speedup vs Python: 1.212x

## Interpretation

The current map2 planner-only workload is small enough that both implementations scale nearly linearly over this sweep. The C++ core is consistently faster, but this smoke does not yet capture the heavier costs expected from reservation checks, rolling replans, fault recovery, and large active queues.

## Gate Status

- A* bottleneck evidence: preliminary planner-only evidence produced.
- Large-scale RL target: not yet defined from full event-simulation pressure.
- Baseline unfairness risk: documented; later comparisons must include reservation-heavy C++ replay and identical task/fault schedules.
