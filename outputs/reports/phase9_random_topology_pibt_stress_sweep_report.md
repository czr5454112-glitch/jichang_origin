# Phase9 Random Topology PIBT Stress Sweep

Date: 2026-06-24

## Scope

This diagnostic generates additional random DAG-like ICS topologies with different layer widths, branch/shortcut probabilities, and task source/goal distributions. It runs Python and C++ active-bag PIBT replay from the same node, edge, heuristic, and task records.

CSV: `outputs/tables/phase9_random_topology_pibt_stress_sweep.csv`

These are synthetic randomized topology stress rows, not separate real airport maps.

## Stress Rows

| Scenario | Layers | Source/Goal | Tasks | Edges | Faults | Config | Py/C++ planned | Py/C++ decisions | Py/C++ conflicts | Mean diff | C++ speedup | Parity |
|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| random_topo_seed211_wide_uniform | 3-4-4-3-2 | uniform/uniform | 36 | 35 | none | none | 36/36 | 200/200 | 0/0 | 0.000000000000 | 1.385 | True |
| random_topo_seed223_skewed_bottleneck | 4-3-5-3-2 | skewed/skewed | 40 | 39 | none | nodes=10:2;13:2;14:2; merge=0->6:106;1->6:106;2->6:106,headway=0.25 | 40/40 | 166/166 | 0/0 | 0.000000000000 | 0.690 | True |
| random_topo_seed227_burst_repair | 3-5-3-5-2 | burst/alternating | 42 | 42 | 3->15@[4.000,18.000) | nodes=3:2;11:2;13:2; merge=5->11:111;9->11:111;10->11:111,headway=0.0 | 42/42 | 168/168 | 0/0 | 0.000000000000 | 0.618 | True |
| random_topo_seed229_static_alt | 4-4-4-4-3 | alternating/uniform | 44 | 44 | 10->12 | merge=4->9:109;5->9:109;7->9:109;8->18:118;12->18:118;13->18:118;15->18:118,headway=0.0 | 44/44 | 311/311 | 0/0 | 0.000000000000 | 0.602 | True |
| random_topo_seed233_shortcut_dense | 5-5-4-5-3 | skewed/alternating | 48 | 69 | 6->10@[3.000,12.000);12->18@[8.000,20.000) | nodes=6:2;10:2;14:2; merge=5->18:118;6->10:110;7->10:110;8->10:110;9->10:110;10->18:118;11->18:118;12->18:118;13->18:118,headway=0.25 | 48/48 | 191/191 | 0/0 | 0.000000000000 | 0.727 | True |
| random_topo_seed239_sparse_repair | 3-3-3-3-2 | burst/skewed | 34 | 22 | 3->8@[4.000,18.000) | none | 34/34 | 245/245 | 0/0 | 0.000000000000 | 0.579 | True |

## Gate Status

- random topology rows: `6`
- total tasks: `244`
- distinct layer layouts: `6`
- median planned rate: `1.000`
- median C++ local-call speedup: `0.654x`
- random-topology PIBT Python/C++ summary parity: PASS
- random-topology PIBT post-shield safety: PASS
- real heldout airport map: not covered

## Remaining Work

- broaden beyond DAG-like synthetic topologies to real heldout airport maps when fixtures are available
- repeat stress timing on multiple machines before paper-grade throughput claims
