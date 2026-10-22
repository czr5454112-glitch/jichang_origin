# Runtime005 unified ledger audit

`unified_order_audit_005.py` is an independent, offline artifact producer. It
reuses the immutable runtime005 `audit_unified_order_book` and adds checks on
raw rows before dictionary joins could hide duplicates. It does not start
native, dispatch policy, alter accounting, unlock TEST, or modify frozen files.

The prerequisite is all 28 full DEV runs in the four registered workflow005
phases: bridge, bins, period and predictor. The same reviewed registration and
closure guards used by `final_science_audit_004.py` are reused and hash-bound as
an explicit producer dependency. That scientific report remains a separate
artifact with its own no-ACK declaration.

Check-only is the default and reads no ACK contents, including when runs are
pending. Execute first verifies runtime005 source bytes, the source and plan
`worker_evidence_contract`, complete native closure, the worker's compact-export
scope, and every ACK file's recorded compressed size. Each compressed file must
be **strictly smaller than 30,000,000 bytes**. A bounded decoder additionally
rejects JSON larger than 300,000,000 bytes, duplicate JSON keys, extra owner
history fields, and altered subset schemas. Source003 is rejected before any
ACK content read. Its large ACK histories are neither needed nor read by this
audit; previous source003 evidence keeps its own existing scope.

Each of the 20 TF runs is audited against its serialized upper order book for
REAL_DEMAND_SUPPLY, NECESSARY_CLEARING, ORDINARY_RETURN and FORECAST_REPOSITION.
Zero categories remain explicit, and zero-denominator ratios are null. Planned
but unsubmitted orders remain in their own category and are excluded from the
actual submission denominator. The optional category alone is not evidence of
forecast guidance, forecast quality or service improvement.

The eight C00/C10 runs have no serialized upper order book in runtime005.
They are explicitly marked `upper_order_book_not_instrumented`; no order ID is
synthesized. Their real submitted/native/client-ledger request sets are checked,
and classification uses only the original payload's explicit control reason.
Optional inventory reposition remains `baseline_optional_inventory_reposition`,
and unsupported reasons remain `unclassified`. Original payloads and outcome
chains are retained in the compressed per-run artifact. Baseline and TF
denominators are aggregated separately.

Additional checks cover duplicate first submissions/native rows/client ledger
rows/order identities, exact retry payload identity, four soft-time fields in
every transfer payload, unchanged order/payload/client-ledger expiry, real
request-set equality and owner scope. Native terminal transfer rows do not
contain expiry; no missing field is invented. ACK owner comes from its enclosing
owner view. ACK time, sequence, attempt, delivered copy count and the native
`PROTOCOL_ACK_DELIVERED` receipts must agree. Final physical receipt and last
delivered ACK state remain distinct, including cancellation overrides.

The producer, dependency, source and all consumed evidence are bound before
consumption and rechecked at completion. Output must be a fresh directory.
Partial work has `pending.json` only. Each full request chain is stored in a
per-run gzip file, while `unified_order_summary.json` holds denominators and
violations. `COMPLETE.json` means the audit finished, not that its checks passed:
inspect `all_request_audits_passed` and `violations_total`. Neither value claims
a scientific service improvement.

From the worktree, first check readiness:

```powershell
& C:\PROGRAMING\python3.11.9\python.exe outputs/experiments/g31_ics_terminal_flow_20261021/unified_order_audit_005.py --source-manifest outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005/source_manifest.json --workflow outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_005/registration.json
```

Only after all 28 are closed, add:

```text
--execute --output-dir outputs/experiments/g31_ics_terminal_flow_20261021/unified_orders_005_001
```

Pure tests use synthetic compact ACK files, never historical native ACK data:

```powershell
& C:\PROGRAMING\python3.11.9\python.exe -m pytest outputs/experiments/g31_ics_terminal_flow_20261021/test_unified_order_audit_005.py -q --basetemp outputs/uoa005_fresh
```

Successful audit artifacts record
`compact_transfer_ack_subset_read=true` and `full_owner_history_opened=false`.
Check-only records both as false. No actual run ACK was opened while preparing
this helper.
