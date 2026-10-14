# Real conditional-boundary inventory

Fixed outcome-blind selection over all 180 actual Round7 loaded attempts. No simulation or routing search was run. The original 4,352-request main stability experiment is unchanged.

| Scene | Role | Attempts | K=0 | Eligible | Selected | Time | K | Boundary task | Offset |
|---|---|---:|---:|---:|---|---:|---:|---|---:|
| cross_cycle | origin | 6 | 0 | 0 | — | — | — | — | — |
| cross_cycle | continuation | 45 | 0 | 1 | cross_cycle_d0033 | 88 | 4 | cross_cycle:round2:flow0:0 | 2 |
| counterflow | origin | 9 | 0 | 0 | — | — | — | — | — |
| counterflow | continuation | 63 | 0 | 5 | counterflow_d0005 | 23 | 4 | counterflow:round0:flow2:0 | 1 |
| near_full | origin | 12 | 6 | 0 | — | — | — | — | — |
| near_full | continuation | 45 | 0 | 0 | — | — | — | — | — |

Selected 2 states; missing cells 4; all six K=0 attempts are preserved in analysis.json. Prospective grid: 24 full-candidate physical continuations over 6 distinct per-state finite tapes, if authorized separately. Actual physical calls: **0**.

At each selected post-arrivals loaded cursor, target arrival minus now is 1 or 2. The −2 outcome would already have been observed (arrival ≤ now), so it is excluded; cancellation has mass 3/17, unchanged arrival 7/17, and +2 arrival/deadline 7/17. All other pending tasks remain their exact original entries, including every protected task. No forecast or controller state was modified.

This finite single-task conditional slice is a mechanism supplement. It is neither the original 64-draw joint sampling experiment nor a calibrated new joint future law; 3*K is an execution plan, not independent business sample count. Missing cells remain missing, and no costs or old regret were consulted.

Read-only measured CPU 6.296875s / wall 6.382571s; 2551 checks, 0 errors. Imports, authoring and final output writes are outside the measured interval. All checkpoint/metadata/input/source hashes and full legal tapes are in analysis.json.
