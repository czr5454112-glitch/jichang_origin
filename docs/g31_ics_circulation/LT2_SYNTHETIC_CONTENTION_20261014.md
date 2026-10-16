# LT2 synthetic shared-resource diagnostic

Authoritative evidence: `outputs/experiments/g31_ics_lt2_20261014/synthetic_contention_003`.
This is **synthetic mechanism evidence only**. No original-map input, capacity,
FIFO, controller or frozen result was changed. It does not complete an
original-map bidirectional joint controller or establish a new solver.

`research_synthetic_contention.py` declares 12 branches before execution:
four route/transfer cells with two owners and two trays, followed by all eight
subsets in a separate three-tray receiving-capacity factor. Inventory and all
physical contracts are identical within each factor. Native016 SHA256 is
`af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0`.
All 12 native branches reached the common horizon 40 and passed the independent
identity, lifecycle, capacity and headway audit. Source archives match hashes.

## Four-cell route/transfer interaction

Owner A has loaded tray L at node 0, with routes 0→1→3→4 and 0→2→3→4.
Owner B has empty tray E at node 5. A second observed job needs a tray at node 1.
Node 1 has one berth; downstream node 3 and edge 3→4 are shared real resources.
The transfer 5→1 reserves and then occupies the receiving berth, and the second
job loads for three seconds. The route action and the source-side transfer
request are independently constructed from their owner's legal observation.
Owner B has already received A's demand message at the common checkpoint 0.11.

The action product is no route update versus a preference for next hop 2, and
departure window 10 versus 0.11. Each branch submits one immutable transfer at
the checkpoint, including the late-window control. Native execution continues
without adaptive lookup of future results. A common public timer at 39 retries
the identical request payload to obtain a terminal delivered ACK. Forks, final
receipts and costs are offline reference, not online information.

| R1 preference | Transfer window | Loaded completion | Receiver completion | Sum | Zero regression vs control |
|---|---:|---:|---:|---:|---|
| S4 control | 10 | 4.5 | 15.8 | 20.3 | Pass |
| S4 control | 0.11 | 7.021 | 5.92 | 12.941 | Fail: loaded +2.521 |
| 0→2 | 10 | 5.5 | 15.8 | 21.3 | Fail: loaded +1 |
| 0→2 | 0.11 | 5.5 | 6.6 | 12.1 | Fail: loaded +1 |

All four branches complete the same two jobs and physically receive the same
empty tray. Both route actions receive `updated` ACKs and actually traverse
0→2. All transfer terminal `received` ACKs arrive at 39.03. The early transfer
causes the unchanged loaded S4 path to wait at its real receiving constraint;
the route alternative changes how the two loaded flows meet downstream.

The complete-cell interaction is
`12.1 - 21.3 - 12.941 + 20.3 = -1.841 seconds` (within binary floating-point
representation). This demonstrates nonseparable action consequences in this
explicit synthetic domain. It does not imply a novel algorithm. The best
aggregate candidate harms the normal loaded job; the zero-regression rule
rejects all three nonbaseline cells. The protected finite-domain incumbent
remains control. No tolerance was added to admit a regression.

## Three-way receiving-capacity counterexample

A separate factor fixes three empty trays at three B-owned source nodes,
all with permitted directed connections to A's receiving node of capacity two.
All eight candidate subsets use the same stock and checkpoint. This is a
three-tray group, not an undisclosed inventory increase in the two-tray group.

Every one- and two-transfer subset physically executes all selected transfers.
With all three requests, native receives two and rejects the third with
`receiving_full`; that rejection is delivered to the client. All three actions
are retained in the denominator. Thus pairwise feasibility does not imply
feasibility of the triple. This elementary capacity example is a diagnostic
requirement, not a claimed scientific contribution.

The classifier requires a complete common horizon and resolved delivered ACKs.
It does not turn two receipts plus a pending/absent third ACK into infeasibility.
Incomplete horizons, missing/pending/expired ACKs and unrelated rejection
reasons remain unknown. The overcapacity label requires the actual delivered
`receiving_full` reason and matching physical receipt count.

## Validation and next step

`synthetic_contention_tests_002.xml`: eight tests passed, including the native
four-cell interaction, per-job protection failure, all-pairs/triple contrast,
and five unknown-preservation cases. Independent review found the earlier
general classifier could mislabel censored nonreceipt; it was corrected before
the authoritative003 run. Earlier001/002 evidence is retained;002's saved
branches were complete, but its classifier lacked these general guards.

Verified local command (use a new output directory):

```powershell
$env:PYTHONPATH='src'
python -m scripts.experiments.g31_ics_circulation.research_synthetic_contention --binary build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd --expected-binary-sha256 af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0 --output outputs/experiments/g31_ics_lt2_20261014/synthetic_contention_next
```

The next method task is to prespecify an expanded resource/window domain with
protected alternatives and map the same interaction checks onto original-map
multi-tray contexts. This probe supplies neither B3/B4 adaptations nor a new
solver. The full-request 100 ms requirement remains uncertified.
