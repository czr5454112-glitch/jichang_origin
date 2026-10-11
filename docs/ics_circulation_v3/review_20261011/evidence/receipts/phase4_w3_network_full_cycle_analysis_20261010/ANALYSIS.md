# Original-map complete saved-tape and controller-drain diagnostics

18 original cells (17 complete nonempty value grids), 2176 original requests, 1388 physical files.

| Scene / role / time | h80 candidate mean costs | Whole-cycle candidate mean costs | h80-choice regret at drain |
|---|---|---|---:|
| cross_cycle / origin / 2 | 31.775, 31.775, 31.775, 33.65 | 30.5875, 30.5875, 30.5875, 32.4625 | 0.0 |
| cross_cycle / continuation / 5 | 28.75, 28.75, 28.75, 28.75 | 28.5469, 28.5469, 28.5469, 28.5469 | 0.0 |
| cross_cycle / origin / 50 | 38.7, 38.7, 38.7, 38.7 | 28.575, 28.575, 28.575, 28.575 | 0.0 |
| cross_cycle / continuation / 53 | 35.6375, 35.6375, 35.6375, 35.6375 | 27.825, 27.825, 27.825, 27.825 | 0.0 |
| cross_cycle / continuation / 83 | 28.825, 28.825, 28.825, 28.825 | 28.825, 28.825, 28.825, 28.825 | 0.0 |
| cross_cycle / origin / 90 | 29.7, 29.7, 29.7, 29.7 | 29.7, 29.7, 29.7, 29.7 | 0.0 |
| counterflow / origin / 2 | 25.9219, 25.9219, 25.9219, 25.9219 | 141.372, 141.372, 141.372, 141.372 | 0.0 |
| counterflow / continuation / 5 | 28.8406, 28.8406, 28.8406, 28.8406 | 139.834, 139.834, 139.834, 139.834 | 0.0 |
| counterflow / continuation / 41 | 85.9781, 85.9781, 85.9781, 85.9781 | 156.822, 156.822, 156.822, 156.822 | 0.0 |
| counterflow / origin / 62 | 87.6375, 87.6375, 87.6375, 87.6375 | 151.7, 151.7, 151.7, 151.7 | 0.0 |
| counterflow / continuation / 81 | 115.303, 115.303, 115.303, 115.303 | 153.122, 153.122, 153.122, 153.122 | 0.0 |
| counterflow / origin / 107 | 175.206, 175.206, 175.206, 175.206 | 176.319, 176.319, 176.319, 176.319 | 0.0 |
| near_full / origin / 2 | real zero-candidate cell | no fabricated branches | — |
| near_full / continuation / 6 | 25.175, 25.175, 25.175, 25.175 | 14.8875, 14.8875, 14.8875, 14.8875 | 0.0 |
| near_full / origin / 46 | 24.7, 24.7, 24.7, 24.7 | 15.075, 15.075, 15.075, 15.075 | 0.0 |
| near_full / continuation / 49 | 23.95, 23.95, 23.95, 23.95 | 15.1375, 15.1375, 15.1375, 15.1375 | 0.0 |
| near_full / continuation / 81 | 14.6375, 14.6375, 14.6375, 14.6375 | 14.6375, 14.6375, 14.6375, 14.6375 | 0.0 |
| near_full / origin / 90 | 13.7, 13.7, 13.7, 13.7 | 13.7, 13.7, 13.7, 13.7 | 0.0 |

All weights, original K4 candidates, 32 saved futures, planning horizon180 and timed continuation are unchanged.
Task completion, transport drain and controller quiescence are separate times. Idle current-node INFINITY capacity stock remains in the physical ledger.
Counts are correlated request-weighted instances from the same three development workloads; no new independent operational source is claimed.
Per-state candidate regrets are conditional single-intervention diagnostics under timed continuation; summing them does not establish an achievable deployed-policy gain.
Candidate cost vectors, per-group means, components and all flat samples are preserved in samples.json; raw per-request ledger is requests.json.
The old 80-step result is a physical checkpoint comparison only; no RolloutResult was used as a resumable engine checkpoint.
