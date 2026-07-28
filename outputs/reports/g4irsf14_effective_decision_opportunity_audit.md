# G4IRSF14-B Effective Decision Opportunity Audit

Status: `PARTIAL_WITH_EXPLICIT_BLOCKER`.

This audit uses the frozen F2 R3/S1/P2/C0/Q0 control, the complete protected map, unchanged protected task rows, no fault, scale 1.0, and reservation depth 1. It is diagnostic only and cannot promote a performance candidate.

## Four required questions

1. **Why Q1 was equivalent to Q0.** Prior G4IRSF13 matched tiers have aggregate timing equivalence: `True`. The measured Q0 actual choose-bag comparator-opportunity count at the largest available E0 tier is `24609`, so equivalence must not be described as 'no opportunity' when this count is non-zero. This counter is hard-bound to actual comparator invocations (escape-token bypass contributes zero); it is not a ready-set-size proxy and is not a Q1 counterfactual. The exact Q1 changed-order count is not identified by a fixed-Q0 trace: `Q1_CHANGED_ORDER_COUNT_NOT_IDENTIFIED_BY_FIXED_Q0_TELEMETRY`.
2. **Why P2 did not commit more often.** The opportunity trace records `187` P2-applicable junction opportunities, `187` multi-bag slices, and `187` owner-visible slices. Runtime rejection totals remain in the raw summary; the junction opportunity schema does not conflate owner visibility with a causal blocker outcome.
3. **Whether v2-safe advantage is concentrated in cross-source same-time requests.** The frozen-control trace records `181` shared-merge pending opportunities. This is a locally observable candidate / upper-bound signal only, not proof that all cross-upstream requests were atomically visible. It is association only: no matched v2-safe state clone is run in Stage 14B.
4. **How much merge order is event-seq determined.** The largest available E0 tier records `141` local destination-reservation/order observations marked seq-determined and `141` reservations with a later same-time competitor. This is a local ordering proxy, not a destination-owned grant count.

## Runtime integrity

- Largest audited E0 tier: `8192`.
- Stale arbitration events: `0`.
- Superseded arbitration wakeups safely rejected before execution: `0`.
- Microphase global scans: `0`.
- Artificial batch delay: `0.0` seconds.
- E0 blockers: `none`.

## Frozen-E0 external exact oracle

- Status: `PASS_EXACT_EXTERNAL_ORACLE`.
- Isolation: one independently spawned process loads exactly one named `czr005_cpp` pyd; old and new binaries are never imported into the same process.
- Real protected cohorts: `motif | 144`.
- Certificate SHA-256: `5e0c0b7b55dda2447e7fbd6fa84703a5a571c92daa8bd581658621b4fca839d8`.
- Frozen Stage-14A binary SHA-256: `814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7`.
- Instrumented new binary SHA-256: `e10da3f5fcf49d3522eb51e70523b2b8d2d2a747cee07d3991d9f74de1efb233`.
- Clean execution Git commit: `116efc2f692f4d0a3307a377d8c6fa1b5476f846`.
- Working raw source-bundle SHA-256: `7f0c06706fd12c6b2f148700c3280ad4e9bf7cece0ac92481986d0bbeac1aa15`.
- Recorded Git-blob source-bundle SHA-256: `8aa143e4f10d80272a9a6522209e2c28b880bc2847894056f6e619c8fe80c7e9`.
- Exact projection: complete bags, junction state, algorithm summary, trace context, and all event/decision/hold/PIBT/credit/fault traces. Only loaded-binary identity and host-dependent performance observations (time/RSS) are excluded. E0 telemetry is off and every Stage-14B extension field is required absent.
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

## Claim boundary

Raw telemetry is stored only under `.local_archives`; committed tables contain grouped counts and deterministic min-hash samples bound to both compressed-file and canonical-payload SHA-256 values. No NOT_RUN row contains invented performance metrics. `Merge visibility` in this stage is local candidate/upper-bound evidence; the runtime explicitly reports destination merge grant disabled and does not claim an atomic cross-upstream grant. Priority opportunity counts are accepted only under the runtime's exact actual-comparator semantics echo; ready-set cardinality is never substituted.
