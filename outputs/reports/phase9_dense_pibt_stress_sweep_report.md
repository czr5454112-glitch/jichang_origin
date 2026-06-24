# Phase9 Dense PIBT Stress Sweep

Date: 2026-06-24

## Scope

This diagnostic runs Python and C++ active-bag PIBT replay on additional fixed random synthetic ICS-like dense task streams. It focuses on the dense node-occupancy corner cases that previously produced post-shield conflicts in Phase9 synthetic matched rows.

CSV: `outputs/tables/phase9_dense_pibt_stress_sweep.csv`

These are randomized synthetic stress seeds, not separate real airport maps.

## Stress Rows

| Scenario | Tasks | Spacing | Faults | Config | Py/C++ planned | Py/C++ decisions | Py/C++ peak | Py/C++ conflicts | Mean diff | C++ speedup | Parity |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| dense_pibt_seed101_low_spacing | 30 | 0.85 | none | none | 30/30 | 191/191 | 9/9 | 0/0 | 0.000000000000 | 1.687 | True |
| dense_pibt_seed103_low_spacing | 32 | 0.75 | none | none | 32/32 | 173/173 | 9/9 | 0/0 | 0.000000000000 | 0.538 | True |
| dense_pibt_seed107_static | 32 | 0.8 | 4->7 | none | 32/32 | 238/238 | 10/10 | 0/0 | 0.000000000000 | 0.539 | True |
| dense_pibt_seed109_static | 34 | 0.7 | 5->8 | none | 34/34 | 359/359 | 10/10 | 0/0 | 0.000000000000 | 0.577 | True |
| dense_pibt_seed113_repair | 34 | 0.7 | 4->8@[2.000,13.000) | none | 34/34 | 244/244 | 10/10 | 0/0 | 0.000000000000 | 0.559 | True |
| dense_pibt_seed127_multi_repair | 36 | 0.65 | 4->8@[3.000,10.000);8->9@[9.000,20.000) | none | 36/36 | 403/403 | 10/10 | 0/0 | 0.000000000000 | 0.528 | True |
| dense_pibt_seed131_merge_buffer | 36 | 0.6 | 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 36/36 | 323/323 | 12/12 | 0/0 | 0.000000000000 | 0.575 | True |
| dense_pibt_seed137_merge_buffer | 38 | 0.55 | 5->8@[3.000,16.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 38/38 | 433/433 | 11/11 | 0/0 | 0.000000000000 | 0.543 | True |
| dense_pibt_seed139_static_repair | 34 | 0.75 | 4->7 | none | 34/34 | 364/364 | 10/10 | 0/0 | 0.000000000000 | 0.643 | True |
| dense_pibt_seed149_repeated_repair | 36 | 0.65 | 4->8@[3.000,8.000);4->8@[14.000,21.000);8->9@[9.000,15.000) | none | 36/36 | 517/517 | 10/10 | 0/0 | 0.000000000000 | 0.636 | True |
| dense_pibt_seed151_overload | 40 | 0.5 | none | none | 40/40 | 365/365 | 10/10 | 0/0 | 0.000000000000 | 0.551 | True |
| dense_pibt_seed157_overload_merge | 40 | 0.5 | 4->8@[2.000,13.000) | nodes=8:2;9:2; merge=4->7:7;4->8:7;5->8:8;6->8:8,cap=1,headway=0.0 | 40/40 | 435/435 | 12/12 | 0/0 | 0.000000000000 | 0.610 | True |

## Gate Status

- stress rows: `12`
- total tasks: `422`
- median planned rate: `1.000`
- median C++ local-call speedup: `0.567x`
- dense PIBT stress Python/C++ summary parity: PASS
- dense PIBT stress post-shield safety: PASS
- real heldout airport map: not covered

## Remaining Work

- add broader randomized graph topologies and task-source distributions
- add a separate real heldout airport map when fixture data is available
