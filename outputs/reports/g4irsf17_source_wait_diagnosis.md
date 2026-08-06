# G4IRSF17 source-wait diagnosis

## Result

Matched raw bags: **4898**.  H5 minus matched E4/off mean source wait is **+0.149551 s/raw bag**; network time is **-0.058518 s/raw bag** and total TTH is **+0.091033 s/raw bag**.

All deltas are `H5 - E4/off`; negative time is better.  Native explicit-reason telemetry reconciles **100.00%** of the matched cohort's positive additional source wait.

The orderable local-source share is **0.00%** and downstream credit/capacity/merge backpressure is **100.00%**.  The directional 50% gate therefore yields **`I1_BOUNDED_PILOT_AND_START_G2`**.

Run the bounded I1 pilot, while allocating the next causal budget to destination merge/service-token G2.

## Native reason contribution

Native rows are queue-population-weighted aggregate intervals. The table reconciles the matched cohort's global positive H5-minus-off source-wait delta across aggregate native cells in proportion to each cell's positive H5-minus-off bag-seconds delta. Selected bag identities are trace context only; this is not per-bag causal attribution.  Raw native durations remain in the ledger, so this reconciliation is visible rather than guessed.

| Reason | Attributed positive additional seconds |
|---|---:|
| DESTINATION_MERGE_TOKEN | 732.500000 |
| SOURCE_SERVICE_NOT_READY | 0.000000 |

## Top source / blocker / time / leg cells

| Source | Blocker | Hour bucket | Leg | Reason | Seconds | Share |
|---|---|---|---|---|---:|---:|
| 52 | 29 | 6 | storage_out | DESTINATION_MERGE_TOKEN | 704.000000 | 96.11% |
| 52 | 40 | 6 | storage_out | DESTINATION_MERGE_TOKEN | 22.250000 | 3.04% |
| 52 | 29 | 5 | storage_out | DESTINATION_MERGE_TOKEN | 6.250000 | 0.85% |
| 52 | 29 | 7 | storage_out | DESTINATION_MERGE_TOKEN | 0.000000 | 0.00% |
| 52 | 40 | 7 | storage_out | DESTINATION_MERGE_TOKEN | 0.000000 | 0.00% |
| 52 | 40 | 5 | storage_out | DESTINATION_MERGE_TOKEN | 0.000000 | 0.00% |
| 52 | 52 | 8 | unknown | SOURCE_SERVICE_NOT_READY | 0.000000 | 0.00% |
| 52 | 52 | 7 | unknown | SOURCE_SERVICE_NOT_READY | 0.000000 | 0.00% |
| 52 | 52 | 9 | unknown | SOURCE_SERVICE_NOT_READY | 0.000000 | 0.00% |
| 52 | 52 | 6 | unknown | SOURCE_SERVICE_NOT_READY | 0.000000 | 0.00% |

## Same-bag versus transferred waiting

Network time improved for **207** bags, source wait regressed for **184**, and both happened on the same bag for **79** bags.  Positive source-wait regression touched **184** matched raw bags; this count is reported as propagation/transfer breadth, not as proof that every affected bag was causally downstream of the same intervention.

## Publication boundary

Raw `*.source_wait.json`, `*.raw_bag_timings.csv`, and `outputs/runstate/**` files are local resumable telemetry and are intentionally excluded from the repository release.  The committed compact evidence for this diagnosis is `outputs/tables/g4irsf17_source_wait_cause_ledger.csv`, `outputs/tables/g4irsf17_source_wait_topology_attribution.csv`, and this report.

## Gate definitions

* `CONTINUE_I1_SOURCE_ORDERING`: at least 50% of attributed positive added wait is `SOURCE_SERVICE_NOT_READY` or `SUPERVISOR_HOLD`.
* `I1_BOUNDED_PILOT_AND_START_G2`: at least 50% is first-edge credit, destination capacity, or destination merge-token backpressure.
* telemetry coverage below 80% blocks either scientific pivot; a generic `blocked=true` is never converted into a reason offline.
