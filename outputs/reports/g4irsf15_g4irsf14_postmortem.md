# G4IRSF15 / G4IRSF14 mechanism postmortem

## Finding

G4IRSF14 proved that exact-state clone/no-op fidelity and the destination-owned exact-slot capability were implementable. It did **not** produce an action-changing causal label. E4 behaved primarily as request -> immediate exact-slot arbitration -> issue or active-grant rejection -> later request, rather than as a retained pending set competing for the next local service opportunity.

## Answers to the Stage 15B audit questions

1. **Why 335,770 requests but one multi-request boundary?** Requests and arbitration events are exactly equal (`335,770`). There were `178,263` active-grant rejections, peak pending was `2`, and only `1` live eligible multi-request boundary was counted. Together these counters support the immediate-arbitration/retry explanation; they do not support a persistent multi-request queue.
2. **Where did the active-grant rejections occur?** The original-1x evidence retained only aggregate counters. Destination, hour, source, goal, storage/direct, timing band, slack, and bag-class breakdowns are **NOT AVAILABLE**. The destination table contains a single explicit unavailable aggregate plus a separately labeled 144-segment diagnostic; it never extrapolates the diagnostic ranking.
3. **Did immediate issue/reject prevent a pending set?** The counter relationship strongly supports that mechanism diagnosis. It is an inference from exact aggregate counters, not a claim based on missing per-request rows.
4. **Why were 1,011,439 lifecycle rows dropped?** The passive original-1x trace used a bounded lifecycle retention limit of `8,192`. The evidence records truncation and the aggregate dropped count, but not a per-row drop-reason distribution. Increasing memory without a retention protocol is not accepted as the repair.
5. **Why did same-timestamp batching not help?** Twenty motif/144/512/2048/8192 cases executed and passed hard gates. No full mode launched. At 8192, E1 failed `NO_REQUIRED_MECHANISM_CHANGE`; E2/E3 were rejected because p95 loss was `3.0033815000006143` seconds, above the 2-second gate. Standalone batching is frozen as negative evidence.
6. **What is the screening false-positive rate?** It is **not estimable**. Formal action-changing attempts are zero, so neither `0%` nor `100%` is a valid estimate. Screening support remains candidate support only.
7. **What can enter the campaign?** I1 (`41,679` exact source boundaries), I3 (`19,898` conservative lower bound), and I4 (`59,049` conservative lower bound) are supported source families. Their exact target descriptors are not committed and must be rematerialized with the exact screening binary. I2 has only one live boundary; I5 has zero strict applicable boundaries, while its `1,337` prefilters are not PIBT applicability.

## Mechanism boundary

E4 remains a frozen exact-slot safety/capability control. It is not promoted as an effective merge scheduler. The next scheduler design must retain losers as pending destination-owned requests and arbitrate at the next natural local service opportunity without reserving a second edge or reading a future route.
