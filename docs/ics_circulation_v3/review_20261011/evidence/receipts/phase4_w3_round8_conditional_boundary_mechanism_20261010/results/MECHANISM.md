# Conditional-boundary mechanism supplement

Both original-future actual-choice bridges reproduced the frozen Round7 branches exactly. All 24 separately executed support × candidate branches reached controller quiescence with every task observed and complete. No memo reuse or bridge deduction.

| State | Support | Mass | c0 J | c1 J | c2 J | c3 J | Optimal candidates | Actual-choice gap |
|---|---|---|---:|---:|---:|---:|---|---:|
| cross_cycle_d0033 | cancel | 3/17 | 29.700000000000003 | 29.700000000000003 | 29.700000000000003 | 29.700000000000003 | [0, 1, 2, 3] | 0.0 |
| cross_cycle_d0033 | j0 | 7/17 | 29.700000000000003 | 29.700000000000003 | 29.700000000000003 | 29.700000000000003 | [0, 1, 2, 3] | 0.0 |
| cross_cycle_d0033 | j+2 | 7/17 | 29.700000000000003 | 29.700000000000003 | 29.700000000000003 | 29.700000000000003 | [0, 1, 2, 3] | 0.0 |
| cross_cycle_d0033 | finite weighted mean | 1 | 29.700000000000003 | 29.700000000000003 | 29.700000000000003 | 29.700000000000003 | [0, 1, 2, 3] | 0.0 |
| counterflow_d0005 | cancel | 3/17 | 46.7 | 46.7 | 46.7 | 46.7 | [0, 1, 2, 3] | 0.0 |
| counterflow_d0005 | j0 | 7/17 | 50.400000000000006 | 50.400000000000006 | 50.400000000000006 | 50.400000000000006 | [0, 1, 2, 3] | 0.0 |
| counterflow_d0005 | j+2 | 7/17 | 50.400000000000006 | 50.400000000000006 | 50.400000000000006 | 50.400000000000006 | [0, 1, 2, 3] | 0.0 |
| counterflow_d0005 | finite weighted mean | 1 | 49.747058823529414 | 49.747058823529414 | 49.747058823529414 | 49.747058823529414 | [0, 1, 2, 3] | 0.0 |

The only varying task has original arrival-now 1 or 2, so jitter −2 is inconsistent with its absence at the real loaded cursor. Cancellation, unchanged and +2 carry exact masses 3/17, 7/17 and 7/17. Deadline shifts with arrival. All other pending tasks, protected entries, public state, original forecasts/publications, controller, cursor and slow clock remain fixed.

This is an exhaustive finite single-task mechanism slice over two real states; four scene × role cells remain missing. It does not extend the main 64-draw future law, add independent business samples, calibrate uncertainty or establish deployment gains. Costs from different states must not be summed as regret savings.

Pure analysis CPU 7.296875s / wall 7.493585s; 230 checks / 0 errors. Full per-branch service/protection/search metrics and file SHA bindings are in analysis.json.
