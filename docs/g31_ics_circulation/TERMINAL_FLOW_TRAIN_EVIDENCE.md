# Existing TRAIN opportunity and time-scale evidence

`foundation_airport_transport_evidence.py` reads only closed TRAIN runs and writes a fresh result. It does not create native sessions, modify budgets, or submit orders. Output: `outputs/experiments/g31_ics_terminal_flow_20261021/train_time_scale_001.json`. Every consumed plan, receipt, trajectory, observation, decision, call and terminal export has a SHA-256 binding in the output. The source arrival population is verified through its pre-existing bound input.

Run from the research worktree with a fresh output filename:

```powershell
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.foundation_airport_transport_evidence --runs outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/G03_P2101_C00 outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/G05_P2101_C10 outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/G06_P2102_C00 outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/G08_P2102_C10 --output outputs/experiments/g31_ics_terminal_flow_20261021/train_time_scale_002.json
```

| TRAIN run | Post-priority visits | Legal opportunities | Multiple sources + targets | Received / submitted requests | Actual submit-to-arrival P50 / P90 / P95 (s) |
| --- | ---: | ---: | ---: | ---: | --- |
| P2101 C00 | 362 | 80 | 69 | 12 / 23 | 301.174 / 528.803 / 3915.085 |
| P2101 C10 | 362 | 77 | 69 | 11 / 21 | 333.298 / 549.418 / 4291.126 |
| P2102 C00 | 362 | 62 | 52 | 10 / 19 | 286.453 / 377.509 / 407.258 |
| P2102 C10 | 362 | 61 | 52 | 10 / 19 | 286.453 / 377.509 / 407.258 |

All four runs end at 18,000 physical seconds; decision observations include the final endpoint, while arrival-count bins cover [7,200,18,000). The legal-opportunity denominator includes all moves in the common catalogue, independent of B1. There were no one-tray/one-target opportunities. Multiple legal sources/targets do not establish multiple positive-value shortages. One real inspectable public case is P2101, 7200 seconds, domestic owner: 7 source nodes, 14 eligible physical trays, 10 targets and 128 legal tray/OD proposals. The common observation digest is `339e23eeeb708e32e7f9d407af240a141160e8ffe9ede6604b116f52e3c85a4b`.

Selected static transport P50 is 302.981–308.751 seconds across these runs. Submission-to-departure P50 is 2.001 seconds and P95 is 3 seconds. Actual transfer distributions include all submitted ordinary/priority/optional transfers, with explicit failure and unfinished denominators. P2101 contains a real 8032.834-second transfer tail; it is retained. Selected, completed optional moves have almost zero static ETA residual in these gates, which does not certify uncongested performance for all transfers. Receiver fractions are finite-window observations, not eventual success probabilities.

Per-station observed shortage episodes, positive-stock-to-zero intervals, missing-sample counts and gap counts are recorded. They use only local owner sensors; absent or stale remote stock is never filled with zero. These are sampling bounds, with left/right censoring, because post-priority snapshots are not continuous native state. Historical data does not provide full demand-forecast, feature, allocator and submission wall-time decomposition, or queued quantity-plan timing; those fields stay missing rather than inferred from model inference time.

Arrival counts are offline labels derived from the bound input only after a run has closed, and never become policy inputs. Counts retain zero bins and exactly the same population mass at 60/300/600 seconds. For example, P2101 node 95 has 234 arrivals in all three resolutions; zero-bin fractions are 47.22%, 25.00% and 16.67%. This says nothing by itself about forecast accuracy or which bin width improves service. C00/C10 within a parent share arrival labels and are not independent samples. These two synthetic parents share one historical template; independent new real airport days remain zero.

Four focused tests passed: arrival-bin mass and zero denominators; observation gaps/missingness; physical-tray versus candidate-edge counting; empty/nonfinite quantiles. No native starts were added by this analysis. Full-window transport comparisons, timing instrumentation and fixed-allocator predictor evaluation remain separate execution work.
