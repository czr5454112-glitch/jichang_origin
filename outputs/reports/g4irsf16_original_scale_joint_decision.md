# G4IRSF16 original-scale joint decision

Final status: `CAUSAL_LEARNING_NO_GO_WITH_ACTIONABLE_PIVOT`.

The formal offline result is `CAUSAL_LEARNING_MODEL_NO_GO`, and the final audit remains `SEALED_NOT_CONSUMED`. I3 reroute is unauthorized. The I4 D0 artifact is diagnostic-only: `support_authorization_status=NOT_AUTHORIZED` and `model_gate_status=I4_SELECTIVE_MODEL_NO_GO`. H5 also remains diagnostic-only. Learned expansion therefore stays **closed**; F2/H0/R0 remains the runtime default.

## What was and was not executed

The full 43,603-segment E4 shadow passed with frozen F2 actions and no model action execution. The matched E4 diagnostic ladder passed runtime/safety gates through 8,192 segments. No authorized learned candidate existed, so a 43,603-segment learned closed-loop candidate was not run; this is the formal no-go terminal path, not missing positive evidence.

At 8,192 segments diagnostic H5 changed real actions but was `+0.091033238056` seconds per raw bag worse than matched E4/off on the mean. It is not a performance win.

## Comparison boundary

Historical F2 (`41.514218717973414` min) and v2-safe (`41.495306987808917` min) are E0 results. G4IRSF16 labels, shadow, and canaries are E4 destination-merge-request executions. The E0 numbers are context only: no strict E4-over-E0 win is evaluated or claimed.

## Actionable pivot

Priority: `I1_SOURCE_ORDERING` with status `ACTIONABLE_HYPOTHESIS_NOT_AUTHORIZATION`. At the matched 8,192 run, source wait shifted `+0.149550837076` s/raw bag, network time shifted `-0.058517599020` s/raw bag, and total mean shifted `+0.091033238056` s/raw bag. This supports testing a bounded I1 source-ordering causal campaign before another I3/I4 threshold sweep; it does not authorize I1 online.

G2 remains blocked until a preregistered merge/service causal-concentration gate shows enough beneficial support. That gate has not been evaluated in the current panel, so no G2 action is authorized.
