# Full TRAIN005 time-scale audit — preparation only

This is a prepared offline producer, not a completed TRAIN result. No actual
TRAIN/DEV analysis, native invocation, or ledger mutation was performed during
preparation. The root offline budget wrapper must register and execute it.

## Fixed interface and budget

From `C:/PROGRAMING/czr005/.g31_ics_circulation_worktree`:

```powershell
C:/PROGRAMING/python3.11.9/python.exe -B outputs/experiments/g31_ics_terminal_flow_20261021/full_train_time_scale_audit_005.py --source-manifest outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005/source_manifest.json --workflow outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_005/registration.json --execute --output-dir outputs/experiments/g31_ics_terminal_flow_20261021/full_train_time_scale_005_001
```

Omit `--execute --output-dir ...` for binding/closed-worker checks only. Suggested
external hard timeout: **1200 seconds**; evidence estimate and enforced output
limit: **128 MiB**. The producer does not itself manage process timeout or budget.
The output directory must be new. It writes two parent gzip reports,
`full_train_time_scale_report.json`, then `COMPLETE.json` last. Failure may leave
`pending.json` and partial files; these are never a completed result.

## Identity and input boundary

Only `full_train_005` in workflow005 is accepted: P2101/P2102, TF-B1-300,
TRAIN, activation 7200, closed physical horizon 59400. Workflow, source manifest,
and both registered plans have literal SHA256 pins. Plans, inputs, receipts,
worker reports, observations, decisions, calls, trajectory and compact terminal
evidence are hashed before consumption and rechecked before COMPLETE. Worker
and receipt must agree; trajectory/native physical closure and all trajectory
decision/observation identities are checked during execution.

The driver is self-contained and does not import the changing final-science
producer. Pure helpers are imported solely from source005 after manifest file
verification; all imported helper bytes and driver bytes are recorded and
rechecked. No native constructor, dispatcher, budget writer, or large owner ACK
history is invoked/opened.

Observations, decisions and calls use the frozen root-array streaming reader.
Trajectory/terminal top-level arrays use a bounded stdlib stream reader, parsing
and discarding unrelated arrays and checking the full JSON/gzip tail. Small
native request metadata, selected trajectory identities, actual arrivals and
own-sensor station samples are retained. No full observation or decision history
is materialized.

## Report meaning

- Actual labels are unique native `BAG_ARRIVAL` receipts. Input jobs only validate
  their identity, station, timestamp and prefix completeness. Missing receipts
  fail the audit; planned jobs never fill missing labels. Counts use
  `[7200, 59400)` at widths 60/300/600 with every zero bin included. Each parent is
  counted once. Pooled bins are descriptive parent-station cases.
- Every recorded nonretry transfer call in the window contributes to an actual
  request denominator. Native transfers without a recorded call are counted
  separately. Received, failed, live right-censored and unknown-native outcomes
  remain distinct. Native `undelivered` is a live state. `status == received`
  must agree exactly with a nonnegative received timestamp. Failed requests are
  never reclassified as censored; unknown outcomes remain unknown.
- Timing P50/P90/P95 use frozen interpolation and retain denominator/missing
  counts. All selected predictions and all actual requests are reported
  separately. A third explicitly matched received subset compares estimated and
  actual decision-to-arrival durations on identical selected request identities.
  Received-only distributions retain their survivor selection limitation.
- Real submission→departure, submission→first edge, first edge→receive and
  submission→receive are separate. Decision→submit and order proposed→submit
  use recorded timestamps. Plan creation→submit requires both matching order
  identity and the same tray/source/destination in that plan's dispatch profile.
  A fallback action absent from the original plan cannot inherit its queue age;
  a later replan cannot fulfill an old plan.
- Loader shortage and legal-source depletion use only local known samples.
  Missing/unknown expected ticks are counted, never filled with zero or bridged.
  Episode onset/cessation intervals are sampling bounds under an explicitly
  stated no-unobserved-reversal assumption; exact continuous duration is unknown.
  The first sampled shortage is not asserted to be the first physical shortage.
  Recorded selected-destination exact forecast shortage offsets are reported;
  all-station forecast first-shortage lead is unknown from this retained scope.
- Existing callback stage records are preserved. Unique plan solve durations
  are deduplicated by plan ID. Pooled callback counts/totals are summed, while
  pooled quantiles remain unknown because raw per-callback durations were not
  retained. Submission wall time is unknown. Catalogue, submission, native
  advance and final export are excluded from callback stage timing; no complete
  request 100 ms certification is inferred.

The two synthetic parents derive from one historical template. No independent
airport-day, significance, service promotion, TEST unlock or R1 claim is made.

## Preparation checks

`test_full_train_time_scale_audit_005.py` uses only small explicitly synthetic
fixtures under `outputs/full_train_time_scale_synthetic_tmp_*`. Its 24 tests
cover JSON/gzip truncation, duplicate keys, finite values, item bounds, receipt
completeness, identity/clock mismatches, terminal status consistency, survivor
denominators, missing sampling, zero bins, horizon exclusion, unchanged byte
bindings, pooled quantiles and two-parent aggregation. It includes a tiny full
stream pipeline and fallback queue-identity negative test. Latest receipt:
`full_train_time_scale_pure_003.xml`; `--help` was also checked. These are producer
guards, not scientific evidence from the actual TRAIN runs.
