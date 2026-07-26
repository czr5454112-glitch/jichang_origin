# G4IRSF12 Denominator Reconciliation

Status: `VERIFIED_DENOMINATOR_MISMATCH`.

This append-only audit supersedes the old Phase-J performance-target interpretation. It does not modify the sealed runtime ledger, result hashes, safety evidence, or formal execution provenance.

## Root cause

G4IRSF8 labelled `inputdata.jsonl:pass_time` as `original_entry_time_tth`. G4IRSF12 correctly introduced the distinct raw-task `original_entry_time` and included the scheduled dwell before later storage-out segments become eligible. Directly comparing the new raw-entry mean with the old pass-time-anchored targets therefore added a fixed input-side offset only to the candidates.

```text
scheduled_pre_release
  = mean_task(sum_segment(pass_time - original_entry_time)) / 60
  = 37.371001534322012 min

matched raw-entry target = legacy target + scheduled_pre_release
v2-safe = 41.495306987808917 min
HCA*    = 43.135938280418159 min
```

The offset is computed from the protected 43,603-segment / 28,506-bag population. It is fixed by the input and is not algorithmic queueing.

## Corrected matched comparison

| Candidate | Raw-entry mean | vs frozen v2 | v2 gate | vs historical HCA* | HCA gate | Safety/termination | Joint gate |
| --- | ---: | ---: | --- | ---: | --- | --- | --- |
| J_F1 | 41.544748409 min | +2.966 s | FAIL | 1.591190 min faster | PASS | PASS | FAIL |
| J_F2 | 41.514218718 min | +1.135 s | FAIL | 1.621720 min faster | PASS | PASS | FAIL |

## Decision

- The new event framework plus bounded-local decentralized coordination beats the parsed historical HCA* comparator on the matched raw-entry denominator.
- It does not strictly beat frozen v2-safe: F1 and F2 miss by only about 2.97 s and 1.13 s per raw bag, respectively.
- It also beats the matched PIBT-off runtime control on completion and deadlock behavior. The control completed 4,189/28,506 bags with 32 unresolved deadlocks before the event limit.
- The PIBT-off control is event-limit censored, so its TTH is not comparable. The five repeats establish deterministic reproduction, not five statistically independent trials.
- The strict joint promotion gate remains FAIL and G4J remains CLOSED. Phase-K remains UNKNOWN_NOT_COMPUTABLE and Phase-L remains BLOCKED_NOT_RUN.
- HCA* remains parsed historical evidence rather than a fresh same-machine rerun, so this is not a final paper-superiority claim.

## Evidence bindings

- Protected input SHA256: `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f`
- Sealed Phase-J ledger SHA256: `0263e022a32936423023013d6eaaa2e3140e44757280ef84c67cf91b59986f0c`
- Legacy denominator table SHA256: `d496e733c247092d03ed247ca524f1ec83a63cfab5d64adcd4c64fd2a7b653f6`
- Sealed Phase-J candidate bundle SHA256: `d886127f1a04def63e1bab54751385f088e68598500863c61c14a35368bd6756`
- Preserved formal source bundle SHA256: `eca01993a9094c8e86558d15246628acd3162d5d769916ded6365ec6437f0df7`
- Reconciliation SHA256: `d8a577bf1540236d90280440a2a92a01f38abf173fca1fbbffdac8289b544f17`

The old 41.5-minute observations remain valid. Only their direct comparison against 4.124/5.765-minute legacy targets and the derived HCA blocker are superseded.
