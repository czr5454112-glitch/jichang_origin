# G4IRSF14-C Same-Timestamp Event Microphase A/B

Status: `PARTIAL_WITH_EXPLICIT_BLOCKER`.

Only event semantics vary. Every case freezes R3/S1/P2/C0/Q0, uses no fault, preserves scale 1.0 and reservation depth 1, and processes only nodes activated at the exact simulation timestamp.

## Ladder

- Executed or cached cases: `20`.
- Hard-gate PASS cases: `20`.
- Batched cases with a required mechanism change: `4`.
- Best 8192 batched mode: `NONE`.
- Full modes actually launched: `none`.
- Frozen-E0 external exact oracle: `PASS_EXACT_EXTERNAL_ORACLE`; certificate `5e0c0b7b55dda2447e7fbd6fa84703a5a571c92daa8bd581658621b4fca839d8`; real cohorts `motif | 144`.
- Original 1x is never launched without `--allow-full`; when launched, only E0 and the single best 8192 batched mode are admitted.

## Frozen-E0 projection audit

- `motif` common old=new algorithm projection: `4bb0ae38ea0842ea701654c9f726d64ff420d156713f6654e98d492a0e84c70a`.
  - bags: `7ec33eb51a10f50b1d8525cb2fb14eaf83d202dff315e7b4873d6bd806c9d187`; count `96`.
  - junction state: `b133e2ba940907824207fdce4ed67c0b158418127a8f2e40de597091698f60c3`; count `46`.
  - algorithm summary: `9a9b2fd3adc55115d98066157f2d26b067c6386a0cfa49afb4e5bd2282ed1a35`.
  - trace context: `ef4ee674cb494a8b9e69dbbb12dd50055b49067e58c0b2c1aecd99130c126bd7`.
  - complete trace payload: `6369e1f76137976b02817b15bfd3ad6f7c03551442932ee0a753ae05c407c0b0`; lengths `{"credit_events":0,"decision_trace":804,"decisions":804,"events":9901,"fault_events":0,"hold_attempts":45,"pibt_events":0}`.
- `144` common old=new algorithm projection: `8888944406c183377268bf8c90bf8df7d22c923bffe80b9aeedb2ae7ce9475d3`.
  - bags: `6267aae9ef2475e803bec4b9e3764522379f258635b2e0011ba6ee4f841b4152`; count `144`.
  - junction state: `a42991d4a8f7bc57e83273bd2e138645cf569695c574b80d2756508024e86718`; count `45`.
  - algorithm summary: `882c079fc623db1987cdc54ac2584eb469afd5733da13eefeb5a100f297a1b15`.
  - trace context: `0c1b7ed2cd407ed36d3f40bcf2e06db962ac32abcd60c398d3377a5730f033df`.
  - complete trace payload: `c8e1d7c30e52362b05644257064e571c1d6761abeea6c1916f192ff91f6c820d`; lengths `{"credit_events":0,"decision_trace":989,"decisions":989,"events":12621,"fault_events":0,"hold_attempts":100,"pibt_events":0}`.

## Gates

A PASS requires complete drainage, zero conflict/unsafe/A*/global-scan/future-route/deadlock/stale-arbitration counts, reservation depth 1, no event/time limit, zero artificial delay, exact runtime echoes, exact binary identity, and complete telemetry accounting with zero dropped rows. The priority counter must explicitly identify actual choose-bag comparator invocations with escape-token bypass equal to zero.

A batched mode advances only when at least one of actual Q0 comparator opportunity, local merge-visibility candidate evidence, event-seq independence, P2 feasible-slice proxy, or TTH/tail improves against denominator-matched E0. Mean loss >1 s/bag, p95 loss >2 s, or p99 loss >4 s is an early reject.

## Negative evidence

- `NO_REQUIRED_MECHANISM_CHANGE`
- `P95_LOSS_GT_2S`

## Claim boundary

Stage 14C establishes event-semantics mechanism evidence only. It does not establish a destination-owned merge grant, causal matched intervention, learned policy promotion, or scale unlock.
The merge-visibility counters are local observable candidates / upper bounds and are not an atomic cross-upstream request set.
