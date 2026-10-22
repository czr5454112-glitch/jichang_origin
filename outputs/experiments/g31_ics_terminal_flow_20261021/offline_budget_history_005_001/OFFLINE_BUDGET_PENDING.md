# Final offline execution accounting — pending

Prepared only. No wrapper invocation, real runner interval, native run, ledger rewrite, model fit, DEV evaluation or scientific report is produced by this preparation. Pure tests use synthetic files and mocked ledger append/resource supervision.

`outputs/terminal_flow_offline_budget.py` runs six exact Python argv entries in `offline_budget_spec_005_pending_001.json`: granularity, final science, unified order audit, the separate four-parent C10-to-TF-B1-60 per-bag strong-baseline audit, frozen full-TRAIN forecast holdout on DEV P2201 C00, and figures from the final-science COMPLETE marker. Every task's source and argv are pinned. The additional four pairs do not alter final-science's existing 24 pairs or the figure schema. All scientific outputs remain pending. No retries, parameter changes, model fitting, TEST access or native admission are available through these task kinds.

The template intentionally has `ready=false`, and null hashes only for the future full-TRAIN model and workflow completion. Once the entire native workflow has closed, root may freeze those two bindings without changing argv/parameters:

```powershell
& C:/PROGRAMING/python3.11.9/python.exe outputs/terminal_flow_offline_budget.py --seal-template outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_spec_005_pending_001.json --output outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_spec_005_ready_001.json
```

Sealing and the optional default `--spec <ready-file>` check are read-only with respect to the ledger; neither runs scientific work. Do not confuse this administrative preparation with a charged execution interval. Any additional unmetered campaign jobs after the historical cutoff require a new explicit holdback record; do not silently claim they were charged.

When no runner or unfinished native attempt exists, root may explicitly execute:

```powershell
& C:/PROGRAMING/python3.11.9/python.exe outputs/terminal_flow_offline_budget.py --spec outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_spec_005_ready_001.json --execute --output outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_execution_005_001
```

The bound workflow completion and its evaluation must certify full closure; each scientific helper still checks its own source/run receipts. The full-TRAIN fit must supply exactly 580 mature training rows and the exact model file used by holdout. The ready spec is immutable. Changed producers or newly selected output paths require a fresh, explicitly reviewed spec; existing partial outputs are never overwritten or silently resumed.

The wrapper opens one interval with the original `foundation_airport_joint_budget.append`, covers source/producer validation, fresh interpreters, child work, supervision, report writing and exit checks, then closes the interval using the same process. It never calls native `admit`. The exact interval is authoritative in the original ledger. `CLOSURE_READY.json` means the tree has been proven closed and the runner is about to close; it does not replace the actual ledger close event.

The historical holdback uses the original campaign budget registration as a conservative lower bound for this task's startup. This is explicitly **not** a recovered actual task startup timestamp. Its entire calendar interval through cutoff is reserved without subtracting native or already-metered work; this may substantially double count. It is not a measured active-time debit, does not alter the original ledger, and is separately added in every preflight. The original ledger prefix SHA/length is retained and must still match on later execution.

Small read-only/preparation work performed concurrently inside an already open native runner interval is already covered by that active wall-clock interval; CPU time is not added again. The holdback concerns an upper bound on *potentially unmetered* work and does not assert that every earlier offline task was separately uncharged. After the cutoff, a native chain with no closed-runner gaps covers concurrent preparation in the same way. Further heavy offline audits use this wrapper; final documentation/publication work, if separately metered, uses a real live non-native runner interval rather than leaving a dead runner artificially open.

Time admission is charged active seconds + history holdback + offline hard-time allowances + any remaining-work reservation <= 172,800 seconds. The pending final-only template reserves 9,000 seconds for six tasks and wrapper overhead and uses zero remaining native time because a closed workflow is mandatory. The preparation calculation separately reserves every currently unclosed/unstarted source005 native task at its full registered hard bound, plus the pending 300-second TRAIN fit allowance. Open native tasks are deliberately counted at their entire hard bound in addition to already elapsed runner time.

Evidence admission counts both `cycle_001` and ROOTDATA, excluding overlapping roots, under 40 GiB. New outputs and remaining workflow evidence are reserved; free disk after reservations must remain at least 30 GiB. Runtime checks retain a 512 MiB growth margin. Periodic measurements cannot guarantee zero overshoot from a single sudden write or a machine-level stall; the fixed task timeouts, explicit job memory limit, disk margin and cleanup reserve reduce this risk. Hitting a limit preserves partial evidence and stops the sequence; it does not certify science.

The existing hash-bound administrative `offline_owned_resource_001.py` supplies a non-inherited Windows JobObject, stdin release gate, hard job commit limit, resource samples, timeout/cancellation and proof that the direct child was waited and the job's active-process count became zero. The policy is supplied by this spec, not inherited from the older experiment. Job committed memory is distinguished from direct-child RSS. A successful leader exit with leftover descendants is a failure. A verified closed tree permits closing the charged runner even after timeout or failure; an unverified tree or supervisor exception leaves the runner open for explicit dead-process recovery. Failed/partial scientific directories remain intact.

No fixed timeout is presented as a scientific convergence or quality criterion. If a bound is insufficient, retain the failed attempt and its charge; any later allowance revision needs an explicit new spec within the same original budget.

The Windows hard timeout bounds each owned child tree. The wrapper's aggregate allowance is also checked during children and after the final source/identity/disk checks; exceeding it produces PARTIAL rather than EXECUTED. Python-side admission and exit bookkeeping are not protected by an external hard-kill supervisor, so this is not described as a hard bound on every possible wrapper stall. The 300-second wrapper allowance reserves tail validation/cleanup; actual time through the final ledger close is charged even on a tail timeout.
