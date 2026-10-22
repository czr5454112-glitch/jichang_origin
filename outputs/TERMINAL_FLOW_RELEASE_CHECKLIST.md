# Terminal-flow final publication checklist

This helper creates a review manifest, immutable journal/log snapshots, and an
exact NUL-delimited Git pathspec. It never starts native execution, changes the
Git index, commits, pushes, or edits any frozen runtime files. No final
package should be generated while the registered workflow is still running.

## Scope

- The original seven tracked modifications: the project README/RESEARCH_STATE,
  joint_calendar_prepared, joint_campaign, joint_control, protocol_v2, and
  protocol_control.
- The narrowly authorized inventory_projection receipt/capture correction, plus
  final appendices to RESULT_INDEX.jsonl and NOVELTY_LEDGER.md: ten permitted
  tracked paths in total. The two research records must preserve HEAD bytes
  exactly. Their only permitted changes are this turn's reviewed final entries.
- New terminal/transport source, corresponding tests and terminal-flow docs;
  output helper scripts and XML/test evidence with the explicit terminal/forecast
  filename patterns in `candidate_paths`.
- CYCLE/terminal_flow registration and audit files, every TF_* task directory,
  exact referenced parent inputs, mappings, runtime calibrations and budget.
- Exactly two old-chain tasks present at handoff:
  JOINT_bridge_R0_legacy_P2201_001 and JOINT_bridge_R0_joint_bridge_P2201_001.
  Their explicit light-file roster includes plans, original receipts, any worker
  reports, progress/log snapshots, terminal/trajectory/cost evidence, calls,
  decisions and support bindings. Exact input/source-manifest/mapping/calibration
  references and the five named old stage registration/dispatch/log files are
  also included. No other JOINT task or arbitrary stage file is swept in.
  The legacy task closed at 59,400 seconds; the bridge task retains its
  unknown_missing_export failure, exit 1073807364, and absence of worker/terminal
  export. Neither a cause nor successful closure is inferred for that failure.
  Their existing native charges and runner closure remain in the shared ledger.
  The already-included terminal_flow/supersession_001.json records that old
  action-Q future dispatch was superseded and no formal action-Q fit started.
- Every terminal_flow_runtime source manifest and its paired ZIP archive,
  discovered dynamically (001..005 for this release). Numbers must be contiguous
  from 001, no source or archive may lack its partner, and the explicitly selected
  workflow must bind the latest source. Every archived member is checked against
  its manifest before publication.
- All reports/models under outputs/experiments/g31_ics_terminal_flow_20261021.

Historical unrelated audit/output scratch directories are excluded. Any tracked
change outside the ten-file roster or unrelated untracked scripts/tests/src
file prevents finalization, so another author's work cannot be silently staged.
No ownership can be inferred from Git alone; this is a path-based isolation check.
The two historical tasks' observations, control_trace and full ACK files are
outside this exact whitelist entirely: they are neither decompressed, hashed nor
published by this exception. Referenced hashes in derived reports alone were not
treated as copies of the missing original light evidence. The prior helper and
tests bytes used by existing short probes remain in
outputs/experiments/g31_ics_terminal_flow_20261021/publication_helper_history005_001,
with their original paths and SHA-256 values in index.json.

The original observations.json.gz and control_trace.json.gz always stay local.
Legacy/full owner delivered_ack_evidence.json.gz histories also stay local. A
compact transfer ACK subset is publishable only after all of these checks:

- Its compressed file size is strictly below **30,000,000 bytes** (decimal; a
  30,000,000-byte file is excluded). This check runs before gzip decompression.
- Its own plan and hash-bound source manifest both explicitly declare
  `deferred_complete_intermediate_results_and_transfer_ack_subset_v1`. Missing,
  legacy, changed or unknown source contracts are rejected before reading ACK data.
- Every owner view has exactly schema, now, owner_id, scope,
  delivered_transfer_acks, client_transfer_ledger and evidence_scope. The owner key
  and owner_id match, the native view schema and subset schema match runtime005,
  full_transfer_ack_history_preserved/full_client_transfer_ledger_preserved are
  true, complete_owner_protocol_view/online_actor_input are false, the retained
  six fields match exactly, and original_owner_protocol_scope equals scope.
- ACK rows and client transfer ledger rows have only the exact scalar fields
  exported by native030. Full command histories, unknown fields, duplicate JSON
  keys and invalid or ambiguous subset declarations cannot qualify.

The guard records publication eligibility; it does not certify causal delivery,
ACK outcome or scientific improvement. The separate unified-order auditor performs
those protocol evidence checks. Its ACK-backed artifact is distinct from the main
final science report's no-ACK analysis. This publication exception does not change
that report's input-scope statement. If subset eligibility cannot be established,
the ACK file is omitted by default and its guard reason remains in the manifest.
No legacy003 giant ACK file is decompressed by this guard.

Every omitted file is recorded with its repository-relative path, SHA-256, size
and omission reason. Files over
95,000,000 bytes also stay local, even when their namespace is otherwise included.
Terminal/calls/trajectory/receipt evidence is included when below that limit.
Finite outcome/protocol audits and the separate unified-order audit can be
recomputed where their required compact ACK files are marked bundled. Complete
public-observation and full owner-history replay still requires the omitted
local files. Native030 and older external dependencies retain their existing
repository/publication references; this package is not a standalone simulator.

## Before finalization

1. All active runner intervals and native attempts must be closed in the original
   ledger. Do not edit or reset the ledger to satisfy this requirement.
2. The explicit active workflow005 dispatch_001.jsonl must end with successor_process_finished or
   dispatch_failed. The helper rejects an incomplete JSONL tail.
3. Review every registered block and orphan TF plan. For complete workflow005,
   its six stages must exist and every task must have an exit-zero, plan-bound
   receipt, identical worker report, and complete registered-horizon trajectory.
4. Preserve workflow004 registration and its two-event dispatch journal ending in
   SupervisorSupersededBeforeDispatch. The helper verifies all six registered
   stage directories and associated plans are absent, no native_start matches its
   source or stage IDs, and the unchanged dispatch is bound by the ledger's
   terminal_flow_unstarted_workflow_superseded event. The supervisor's recorded
   predecessor_native_untouched assertion and hashed recorder must remain intact.
   The manifest reports this as superseded_before_dispatch, scientifically_closed
   false, zero verified starts, and six unprepared stages. It does not call this
   historical workflow a completed run or infer physical actions beyond the
   supervisor and ledger evidence.
5. Write an explicit `release_disposition.json`, normally in workflow_005.
   Historical gate_001 plans that were superseded without execution still need
   individual reasons. A failed/stopped workflow must explicitly retain every
   failed/nonclosed task and every stage that was never prepared.
6. The final operator/root appends and reviews the two final research records.
   This helper does not edit them. Bind each changed record's appended byte suffix
   (excluding every original HEAD byte) and a review reason in
   research_record_appends. No omitted or extra file reviews are accepted, original
   bytes cannot change, JSONL entries must be complete with new unique IDs, and
   each append must end in a newline. Review the semantics against this turn's
   final observed results; the hash gate cannot establish authorship or truth.
7. Finish the service/forecast/case/negative-result reports and final tests first.
   Keep new report producers idle until verification and staging finish.

Disposition schema (replace placeholders with the final observed facts):

```json
{
  "schema": "g31.terminal_flow.release.v1.disposition",
  "registration_sha256": "SHA256_OF_WORKFLOW_005_REGISTRATION_JSON",
  "outcome": "complete",
  "reason": "Fixed development workflow closed; scientific conclusions remain limited to its final audits.",
  "nonclosed_tasks": {
    "EXACT_HISTORICAL_TASK_ID": {
      "status": "not_started",
      "reason": "Superseded preparation; no native start was admitted."
    }
  },
  "unprepared_stages": {},
  "research_record_appends": {
    "docs/g31_ics_circulation/RESULT_INDEX.jsonl": {
      "sha256": "SHA256_OF_ONLY_APPENDED_BYTES",
      "reason": "Final operator reviewed this turn's newly appended final result entries."
    },
    "docs/g31_ics_circulation/NOVELTY_LEDGER.md": {
      "sha256": "SHA256_OF_ONLY_APPENDED_BYTES",
      "reason": "Final operator reviewed this turn's newly appended novelty limits."
    }
  }
}
```

For a documented failure stop use `outcome: stopped_after_failure`, state its
specific reason, and map every missing stage name to its reason. Status is the
receipt's scientific_status, or `not_started`, `missing_receipt_after_native_start`,
or `invalid_closed` as computed by the helper. Extra or omitted acknowledgements
are rejected. A stop disposition does not make a partial run scientifically closed.

## Commands for the final operator

Run from the worktree with the accepted Python 3.11 environment. Inventory is
read-only and can be used while experiments are active:

```powershell
& C:\PROGRAMING\python3.11.9\python.exe outputs/terminal_flow_release.py inventory
```

After all finalization conditions are met, choose a fresh, short output directory:

```powershell
& C:\PROGRAMING\python3.11.9\python.exe outputs/terminal_flow_release.py finalize --workflow outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_005/registration.json --disposition outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_005/release_disposition.json --output outputs/terminal_release_001
& C:\PROGRAMING\python3.11.9\python.exe outputs/terminal_flow_release.py verify --manifest outputs/terminal_release_001/manifest.json
```

Inspect manifest.json, including every omission, compact ACK eligibility/count,
and source ZIP checks. Compact ACK subsets are published; full owner histories
remain omitted. The
active registration, historical supersession audit, and original/appended research
record byte counts and hashes appear in its gate. Historical workflow004 stages
belong to historical_workflows, not the active workflow005 unprepared_stages map.
If a research record is unchanged, omit it from research_record_appends entirely.
The ledger, dispatch journals, progress journals and logs are published as short-named
snapshots under the final directory, not as their active source paths. Original
source paths and content hashes remain in the manifest. The helper checks closure
and journal bytes again after hashing, and rejects files changed during collection.

Only after review and verification should the final operator stage the exact
pathspec; the helper does not run this command:

```powershell
git add --pathspec-from-file=outputs/terminal_release_001/stage_paths.nul --pathspec-file-nul
```

Do not use `git add .`. Inspect staged paths and sizes before committing/pushing.
The pathspec includes literal file entries only. It does not include itself, the
original active journals, unselected historical artifacts, or any large local-only
history. A failed finalization is retained for audit; use a fresh output directory
after fixing its cause instead of overwriting an earlier manifest.

Pure helper tests:

```powershell
& C:\PROGRAMING\python3.11.9\python.exe -m pytest outputs/terminal_flow_release_tests.py -q
```
