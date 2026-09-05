# Nanning 2x tail-risk audit

Schema: `czr005.nanning_2x_tail_risk_audit.v1`
Evidence status: `VALIDATED_DETAILED_REPLAYS_PARTIAL_OR_COMPLETE`
Formal 2x full-population THT: `N/A` (unchanged protocol; no survivor timing).

## Frozen paired result

P1D1 - P0D0 maximum tardiness is **+2555.10 s** with paired-bootstrap 95% CI **[1027.27, 4083.66] s**. P1D1 is worse in **9/10** seeds, better in 1/10, and tied in 0/10.

| Seed | P0D0 max tardiness (s) | P1D1 max tardiness (s) | Delta (s) | P0D0 completed | P1D1 completed | Max-wait delta (s) |
|---:|---:|---:|---:|---:|---:|---:|
| 104729 | 47259.00 | 48468.49 | 1209.49 | 47130 | 56528 | 1495.77 |
| 130363 | 68559.00 | 71559.00 | 3000.00 | 45836 | 55103 | 4149.65 |
| 155921 | 42254.85 | 42785.68 | 530.82 | 47352 | 57012 | 372.18 |
| 181081 | 53109.00 | 59933.13 | 6824.13 | 46875 | 54081 | 6751.66 |
| 205759 | 68559.00 | 66081.79 | -2477.21 | 48254 | 56994 | -2419.71 |
| 232003 | 61809.00 | 67359.00 | 5550.00 | 47919 | 56768 | 3914.94 |
| 257053 | 65409.00 | 68559.00 | 3150.00 | 46297 | 56504 | 3773.35 |
| 283303 | 45490.43 | 46656.74 | 1166.31 | 47077 | 57012 | 1386.08 |
| 308081 | 56859.00 | 60723.41 | 3864.41 | 46247 | 56838 | 2687.54 |
| 333667 | 51351.95 | 54084.99 | 2733.05 | 45775 | 55024 | 2864.45 |

## Strongest supported diagnosis

- P1D1 completes more raw bags than P0D0 in all 10 seeds, yet its maximum tardiness is worse in 9. This is a genuine extreme-tail trade-off, not a claim of overall 2x timing improvement.
- The sign of the seed-level maximum-wait change matches the sign of the maximum-tardiness change in 10/10 seeds; their Pearson correlation is 0.952. This supports a congestion/wait-tail co-movement diagnosis at seed level, but does not prove that both maxima belong to the same bag.
- In 10/20 arm-seed cells, the all-population maximum equals the completed-population diagnostic maximum. Therefore the observed effect cannot be dismissed as only a fixed-horizon penalty on incomplete bags.
- No new scorer, guard, mode, parameter, or routing rule was introduced by this audit.

## Validated per-bag diagnosis

- All-population maximum bags are direct in 20/20 validated arm-seed cells, and source-queue wait is zero in 20/20.
- For those maximum bags, junction-queue wait accounts for 100.000%–100.000% of recorded local wait; merge-grant wait is at most 0.095% of their observed post-admission interval.
- The worst-one-percent cohort is distributed rather than confined to one OD (P0D0: 25 ODs, top-five OD share 48.4%, direct share 100.00%, completed share 63.3%; P1D1: 32 ODs, top-five OD share 43.4%, direct share 99.84%, completed share 85.0%).
- Decision: `EXPECTED_CAPACITY_TRADEOFF_WITH_JUNCTION_WAIT_DOMINATED_TAIL`. `PRIORITY_STARVATION` and `ROUTE_OSCILLATION_OR_HOLD` remain `NOT_IDENTIFIED_NO_TRACE_REPLAY`; the per-bag result replay does not contain the first policy divergence or scorer decomposition.

## Per-bag and trace identifiability

Archived cells contain bag evidence: `False`. The archived native summaries report `trace_limit=0`, `event_trace_limit=0`, `decision_trace_stored_count=0`, and `hold_trace_stored_count=0`. Consequently the original worst bag IDs, OD concentration, direct/EBS split, wait decomposition, and first P0D0/P1D1 decision divergence are not recoverable from the aggregate JSON alone.

Validated detailed rerun cells currently available: `20/20`. See `C:/PROGRAMING/czr005/.feng_cie_dh_worktree/outputs/tables/nanning_2x_worst_bags.csv` and `C:/PROGRAMING/czr005/.feng_cie_dh_worktree/outputs/figures/nanning_2x_tail_od_node_heatmap.png`. When no validated detail exists, the CSV and figure carry explicit unavailable evidence rather than invented task or node identities.

## Reproducible detail path

Run one frozen cell (about the cost of the original cell), then rerun `audit`:

```powershell
python scripts/eval/run_nanning_tail_risk_audit.py rerun-cell --seed 104729 --arm P0D0
python scripts/eval/run_nanning_tail_risk_audit.py rerun-cell --seed 104729 --arm P1D1
python scripts/eval/run_nanning_tail_risk_audit.py audit
```

Each detailed cell is accepted only if binary SHA, workload SHA, paired realization SHA, completion count, fixed-horizon maximum tardiness, denominator, and 2x-THT-N/A contract all match its archived cell. The retained per-bag decomposition reports release/admission/completion and runtime wait components, but marks segment sums as non-additive across EBS legs.

The first policy divergence remains `NOT_IDENTIFIED_NO_TRACE_REPLAY`; bag-result reruns do not masquerade as decision traces.
