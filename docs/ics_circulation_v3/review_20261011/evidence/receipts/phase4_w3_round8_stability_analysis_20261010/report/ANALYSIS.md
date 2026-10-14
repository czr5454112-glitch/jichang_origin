# Conditional future stability: complete frozen analysis

Planned requests: **4352 logical / 2468 unique physical**; 1884 exact aliases retain original draw weights.

State records: 23; complete ranking states 17/17; zero pools 6/6; unknown ranking states 0.

These are conditional simulations on reused development states. Two pseudorandom blocks and repeated future draws are not independent airport operating days. The law is synthetic, not a calibrated forecast posterior.

## Statewise cost and support

| State | Role / time | Distinct / possible futures | Seen law mass | Pooled64 mean range | Actual pooled64 gap | Block32 best sets |
|---|---|---:|---:|---:|---:|---|
| counterflow_d0000 | origin / 2 | 64/65536 | 0.00180964 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| counterflow_d0001 | continuation / 5 | 64/65536 | 0.00188781 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| counterflow_d0014 | continuation / 41 | 63/4096 | 0.0244619 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| counterflow_d0024 | origin / 62 | 61/1024 | 0.0881156 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| counterflow_d0028 | continuation / 81 | 60/1024 | 0.0854141 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| counterflow_d0030 | origin / 84 | 53/256 | 0.267002 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| cross_cycle_d0000 | origin / 2 | 52/256 | 0.27234 | 1.625 | 0 | [[0, 1, 2], [0, 1, 2]] |
| cross_cycle_d0002 | continuation / 5 | 49/256 | 0.239406 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| cross_cycle_d0017 | origin / 50 | 16/16 | 1 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| cross_cycle_d0019 | continuation / 53 | 15/16 | 0.963542 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| cross_cycle_d0030 | continuation / 83 | 16/16 | 1 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| cross_cycle_d0034 | origin / 90 | 1/1 | 1 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| near_full_d0000 | origin / 2 | 52/256 | 0.281202 | zero_candidate_pool_retained | unknown / no action | — |
| near_full_d0002 | origin / 3 | 57/256 | 0.287848 | zero_candidate_pool_retained | unknown / no action | — |
| near_full_d0003 | origin / 4 | 58/256 | 0.289768 | zero_candidate_pool_retained | unknown / no action | — |
| near_full_d0004 | origin / 5 | 58/256 | 0.282679 | zero_candidate_pool_retained | unknown / no action | — |
| near_full_d0005 | origin / 6 | 51/256 | 0.289325 | zero_candidate_pool_retained | unknown / no action | — |
| near_full_d0006 | continuation / 6 | 56/256 | 0.294789 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| near_full_d0007 | origin / 7 | 53/256 | 0.279408 | zero_candidate_pool_retained | unknown / no action | — |
| near_full_d0023 | origin / 46 | 16/16 | 1 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| near_full_d0024 | continuation / 49 | 14/16 | 0.947917 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| near_full_d0036 | continuation / 81 | 16/16 | 1 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |
| near_full_d0040 | origin / 90 | 1/1 | 1 | 0 | 0 | [[0, 1, 2, 3], [0, 1, 2, 3]] |

Zero-pool future supports are retained as inventory only; they have no candidate evaluation. Low seen probability mass alone does not invalidate Monte Carlo estimation, but does not support an exhaustive-future claim.

## Select on one block, evaluate on the other

| Selection draws | Complete / planned state-block choices | Select actual | Held-out mean better / tied / worse | Largest mean harm | Largest mean benefit | Any later completion in held-out block |
|---:|---:|---:|---|---:|---:|---:|
| 2 | 34/34 | 34 | 0/34/0 | 0 | -0 | 0 |
| 8 | 34/34 | 34 | 0/34/0 | 0 | -0 | 0 |
| 32 | 34/34 | 34 | 0/34/0 | 0 | -0 | 0 |

Cost ties within 1e-8 retain the actual analytic action; otherwise choose the lowest ordinal. A second block evaluates the selected action against the actual action on the same futures. Its empirical minimum is only a noisy reference, not the true optimum. State gaps must not be summed as deployment improvement.

## Paired difference variability

| Prefix draws | Nonbaseline candidate-block comparisons | Negative covariance | Undefined independent-variance proxy | Paired/proxy ratio > 1 | Median paired SE | Largest paired SE |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 102 | 0 | 27 | 0 | 0.0 | 1.0 |
| 8 | 102 | 0 | 12 | 0 | 0.0 | 0.32732683535398854 |
| 32 | 102 | 0 | 12 | 0 | 0.0 | 0.1555427542095638 |

These standard errors describe paired Monte Carlo differences within a fixed state and law. The variance ratio uses an estimated independent-draw comparator; no separate independent-random-number experiment was performed, and no universal variance reduction is asserted.

## Per-task service remains a separate outcome

Across 1088 complete state-future draws, 128 have some candidate completion difference. Of those, 76 have an entirely flat J pool.

There are 76 nonactual, J-optimal candidate-draw combinations with at least one later task completion. These are repeated simulation task instances, not distinct operational bags or deadline-miss counts.

Nonactual candidates with no higher J on every one of 64 draws, no later completion on any draw, and at least one earlier completion: 0. This is an offline diagnostic, not a deployable guard.

All individual bag changes, protected lateness, per-draw candidate costs, all tie sets and all selection-block/evaluation-block choices are retained in results/states/*.json.

## Complete finite-support auxiliary expectation

| State | Entire support | Expected candidate costs under declared finite law | Best set | Actual gap |
|---|---:|---|---|---:|
| cross_cycle_d0017 | 16 | 29.0333, 29.0333, 29.0333, 29.0333 | [0, 1, 2, 3] | 0 |
| cross_cycle_d0030 | 16 | 29.0333, 29.0333, 29.0333, 29.0333 | [0, 1, 2, 3] | 0 |
| cross_cycle_d0034 | 1 | 29.7, 29.7, 29.7, 29.7 | [0, 1, 2, 3] | 0 |
| near_full_d0023 | 16 | 14.8667, 14.8667, 14.8667, 14.8667 | [0, 1, 2, 3] | 0 |
| near_full_d0036 | 16 | 14.8667, 14.8667, 14.8667, 14.8667 | [0, 1, 2, 3] | 0 |
| near_full_d0040 | 1 | 13.7, 13.7, 13.7, 13.7 | [0, 1, 2, 3] | 0 |

These expectations use every legal finite-law future with its exact rational probability and recorded floating-point costs. They do not reweight the primary 2/8/32 sample estimates, do not assume unseen costs, and do not establish a real-world probability law.

## Figures and reproducibility

[Candidate value gaps](../visuals/conditional_value_gaps.png) · [Cross-block selections](../visuals/cross_block_selection.png). SVG versions are beside the PNG files.

Read-only extraction receipts bind every compact shard to its raw physical result. The final input binding checks frozen preparation, live source/tests, original inputs and all consumed compact shards before/after analysis. Independent raw and aggregate review is recorded in the separate Round8 review directory.
