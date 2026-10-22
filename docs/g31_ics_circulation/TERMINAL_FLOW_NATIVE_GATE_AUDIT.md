# Terminal-flow native gates: independent chain audit

All numbers below come from completed P2101 TRAIN gates ending at 18,000 physical seconds. They are mechanism evidence, not the full 59,400-second comparison or a held-out service result. The audit uses only immutable receipts and exports; it starts no native sessions and changes no ledger.

The new runtime002 C00 and C10 reproduce their respective old G03/G05 gates exactly for the 360 recorded trajectory decisions, all public-observation digests, all protocol request/reply/time sequences, all 28,506 job records, 22 trays, transfer records, physical receipts and transport legs. The full cost dictionaries and system objective are equal. Export shape adds a `population` field. Frozen source hashes and some registration fields differ, so this establishes equivalence for these actual runs; it does not authorize universal source-version substitution. The two baseline equivalence JSONs list all source and registration changes.

Runtime003 adds priority-submission metadata to the same order book. Its TF-current, TF-B1-60 and TF-B1-300 gates are each physically identical to their runtime002 counterpart, including observation and protocol histories. No short-window action change can be attributed to the priority bookkeeping correction.

| Runtime003 method / order reason | Unique orders = submitted requests = native requests | Accepted | Physically received by cutoff | Failed at export |
| --- | ---: | ---: | ---: | ---: |
| TF-current: real-demand supply | 15 | 15 | 6 | 6 |
| TF-B1-60: real-demand supply | 13 | 13 | 5 | 7 |
| TF-B1-60: extra forecast reposition | 5 | 5 | 3 | 0 |
| TF-B1-300: real-demand supply | 13 | 13 | 5 | 7 |
| TF-B1-300: extra forecast reposition | 5 | 5 | 3 | 0 |

All 15/18/18 request-ID sets match exactly between the final order book, actual non-retry submissions and native transfer export. Source, destination, tray and owner metadata match the submitted payloads. Native departure expiry is unchanged; upper `target_by`, `useful_until`, `plan_valid_until` and `latest_issue_estimate` never enter the native payload. Failed and unfinished requests remain in the denominators.

One real-demand request is physically received at 17,992.833836 seconds while its last delivered ACK, at 17,942.2 seconds, still says `departed`. The controller checkpoint correctly retains `DEPARTED`; the offline audit separately records the physical result. This is not an actor-visible delivery before its ACK arrives.

Each TF-B1 gate has 360 unique rolling plans, only five nonempty plan items, five issued optional orders, five accepted requests and three received optional orders. Cached repeats are counted once per plan ID; items are uniquely scoped by `(plan_id, tray_id, source, destination)`. The optional received/submitted ratio is 3/5, and the realized plan-item ratio is also 3/5 here. All five are additional moves from loader sources. There is **no native ordinary-return, necessary-clearing or multi-item-plan execution coverage in this short gate**; those mechanisms require separate evidence. TF-current's zero optional orders does not suppress its 15 real-demand supply orders.

The first forecast order, tray `initial:24:0`, is proposed from 24 to 26 at 8400 seconds with exact-ETA net proxy gain 37.958792 bag-seconds and physical reception at 8622.162. At 9060 seconds, 134→95 has positive net proxy gain 2.704903 and reception at 9305.453. These are verified request/ACK/receipt chains, not a proof that the proxy predicts complete-system gain.

The 60- and 300-second variants have 360 matching owner/time observations and identical public menus. Their selected actions differ at **zero** of these callbacks. No granularity service benefit follows from this gate. All flow-plan dispatch times are advisory; only actual submission timestamps count as execution.

Evidence lives under `outputs/experiments/g31_ics_terminal_flow_20261021/`: `gate002_C00_baseline_equivalence_001.json`, `gate002_C10_baseline_equivalence_001.json`, `runtime002_vs003_TF-*_001.json`, `gate002_60_vs_300_decisions_001.json`, and `confirm003_TF-*_chain_001.json`. Each chain contains all unique plan items, first-action checks, station tables, order/request joins, delivered ACKs and received events. The files preserve negative coverage and identity-check results.

The real audit entry is:

```powershell
& C:/PROGRAMING/python3.11.9/python.exe -m scripts.experiments.g31_ics_circulation.foundation_airport_terminal_flow_audit run outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/TF_confirm_003_TF-B1-60_P2101 --output outputs/experiments/g31_ics_terminal_flow_20261021/confirm003_TF-B1-60_chain_002.json
```

Use `baseline-equivalence LEFT RIGHT --output NEW_JSON` for replayed-rule comparisons and `compare-decisions LEFT RIGHT --output NEW_JSON` for matching public-state decisions. Outputs must be fresh. Four targeted audit tests pass, covering cached-plan denominators, rejected requests, actual source-category classification, and separation of delivered controller status from final physical receipt.
