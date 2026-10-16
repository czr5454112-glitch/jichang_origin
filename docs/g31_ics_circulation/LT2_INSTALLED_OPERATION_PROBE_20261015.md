# Finite installed-operation accounting probe

This is an opt-in experimental admission contract, not a replacement for the
attached LT2 requirement for actual business-task updates. No production
controller uses it. The prepared campaign has seven fixed synthetic cases and
nine declared roots per arm. Native run 001 and its independent saved-evidence
verification completed; the setup amendment below is required when reading its
timing numbers.

The cases are an installed route, a lost-ACK immutable retry, a stale-route
rejection followed by a fresh replacement child, empty-tray supply, a
cancellation child with a terminal-failed delivery parent, a no-action update,
and an intentionally unresolved ACK. All roots remain in the denominator.
The last case must remain open. Completing a permitted terminal-failure
disposition is not reported as successful delivery.

Admission precedes the actual owner-local observation. The route candidate
uses that observed job and stationary loaded tray plus public graph/service
durations. An independent verifier recomputes the route candidate from the
saved admitted view. Every immutable protocol identity is linked to explicit
roots before submission; retries reuse it, and replacement/cancellation children
are declared before their own observation. A new independent update does not
extend an older root merely because it reads an old reservation.

The operation contract requires actual delivered terminal ACKs, processing,
closure of declared children, a completed same-time native drain and serialized
returned output. Route success means the next-hop intent was installed with
an `updated` ACK; it is not evidence that a complete proposed route executed.
An empty-tray transfer requires `received`; cancellation requires `cancelled`.
The parent of a successful cancellation retains its explicit failed-delivery
disposition. Forecasts and submission replies cannot close a request.

This prototype admits one job per root. Route identity and observed-job scope
are checked. The empty-tray and cancellation cases cannot prove a unique
affected-job assignment, so they remain operation lineages with unverified job
labels. Joint multi-job admission is unsupported. These limitations remain
explicit even if an experimental computation bound is below 100 ms.

For every completed root, the bound is its entire measured outer lifetime plus
the full common mandatory setup. Setup includes fixture/input construction,
native session construction, client initialization and the initial physical
advance. Root lifetimes include actual observation, candidate generation,
selection, validation, serialization, all native calls, ACK polling/processing,
retries, fallback, mandatory drain and returned output. Nested/shared work is
charged in full to each dependent root, never divided. No physics, GC or
scheduler time is subtracted. Simulation-time message delays are advanced by
actual computation; the driver does not sleep for logical transport time.

Capture-contract verification/start, post-service evidence exports and the
independent offline verifier are diagnostics outside those service intervals.
Their costs remain in process wall time. No result is an exclusive native-stage
duration or deployment real-time certificate. The accepted native025 phase
partition is an additional coverage diagnostic; its unlabeled remainder is
retained in the full outer bound.

Each native service call has an ordered tape containing copied arguments,
returned output, physical clocks and wall bounds. Timed envelopes must match
the tape one-for-one. Observations and final drains must refer to actual tape
entries; delivered ACKs must appear in actual queries. The causal ledger is
replayed through its admission/attempt/ACK/disposition/drain/output validators,
including exact contiguous event sequences. Missing, reordered or inconsistent
records fail closed. The plain and timed arms must have identical inputs,
decisions, public observations, immutable requests, protocol outcomes, causal
structure, physical clock and final native seal after removing only specifically
declared instrumentation clocks.

The declared source inventory followed repository-relative and absolute imports
at the repository root, but missed two startup modules resolved through `src/`;
the limitation and current supplement are described below. Archive paths
preserve the repository hierarchy. Every declared source was checked before/after
execution. The accepted native025 reference, contract, build/archive authority
and binary SHA are pinned. Each case gets an immutable in-progress record before
execution and a final assessment afterward. Timeouts, nonzero exits, launch
failures and missing raw cases retain the complete declared denominator and
cannot become successful measurements merely because another worker exited 0.

The resumed draft passed 58 pure checks in
`outputs/experiments/g31_ics_lt2_sustained_20261014/operation_probe_pure_006.xml`.
These cover ledger/tape tampering, missing drain/ACK/attempts, immutable identity,
job scope, source closure, serialization roundtrip and failed process receipts.
A test double also runs the actual no-action driver/bridge/tape/validator path
end to end; it is explicitly not a native-runtime check.
The earlier 16-check artifact covered an earlier draft only. Independent source
review found no remaining concrete blocker. The immutable preparation is
`outputs/experiments/g31_ics_lt2_sustained_20261014/installed_operation_prepare_002/`.
Preparation 001 is retained; 002 additionally binds serialized returned decisions
to the actual saved selections, with a negative omission test.
It creates no native session. The actual run is
`outputs/experiments/g31_ics_lt2_sustained_20261014/installed_operation_native_001/`.
Both serial workers exited 0. All seven cases exercised their declared actions,
and the fourteen plain/timed raw records agree on requests, ACKs, public views,
causal structure, logical clocks and final native seals. The 42 source pins did
not change. Re-reading the raw files produced an identical
`independent_verification_002.json`. Eight roots closed; the intentionally lost
ACK remained open after three attempts. A cancellation parent closed with
`terminal_failure`, which is not successful delivery.

The first report omitted small pre-admission bookkeeping/timer gaps between its
two setup intervals and root admission. The native raw evidence and original
report remain unchanged. The separate
`installed_operation_setup_amendment_003/assessment.json` charges these observed
case-setup gaps through the earliest admission in full to every root (6.5–15.3
microseconds). Its auditor passed 15 pure
checks, including clock/container tampering, open-root and shared-cost guards.
Amendment 002 is retained; 003 clarifies that a later child's earlier parent work
remains in its ancestor's full lifetime and rounds process seconds upward when
converting to a conservative nanosecond bound.

For the initialized-host service contract, the eight closed bounds become
2.3491–8.7324 ms, including common fixture/session/client setup and every native
advance and retry. The missing-ACK root has only a 5.3939 ms known prefix. These
are not unconditional complete-request or original business 100 ms passes.
The per-case full-wall setup sensitivity, which also charges the capture
constructor, is 309.5863–440.8651 ms for closed roots. The still broader
whole-worker bound is 5.6883344 seconds per closed root, without division; it
retains process startup, all seven cases, diagnostics and exports. A conservative
upper bound above 100 ms is not an observed request violation.

The distinction is source-bound. `Native025TimingCapture.__init__` checks the
accepted archive/module identity, starts the offline recorder and obtains its
empty epoch. Its outputs populate timing envelopes and later evidence exports;
they do not enter route candidates, payloads or ACK decisions. The plain arm
never constructs this object and has identical native/public semantics. However,
the worker's earlier `verify_contract` selects the binary used by `load_native`,
and Python imports initialize the host before all case timers. These necessary
host-startup costs are not separately isolated by this campaign, so the
whole-worker sensitivity retains them and no cold-start claim is made.

The largest initialized-host root is empty supply: 7.9087 ms lifetime plus
0.8237 ms corrected setup. Its actual tape contains 55 ACK queries (1.5720 ms),
55 native advances (1.7274 ms), six immutable submissions (0.3727 ms) and one
observation (0.2668 ms). The other 3.9698 ms includes Python lineage validation,
codec, bookkeeping and scheduler gaps. Tape costs include diagnostic copying;
these are outer bundles, not isolated solver stages. The diagnostic is saved as
`installed_operation_setup_amendment_003/outer_cost_diagnostic.json`.

This supports examining repeated unchanged ACK polling on real original-map
requests. It does not justify removing retries, skipping mandatory drains,
relaxing job scope, or using an owner-activation mean as a request measurement.
The next original-map probe must declare its actual notification admission and
continuation contract before any observation or candidate construction.

A later source-closure audit found that `src/czr005/__init__.py` and
`src/czr005/cpp_backend.py` were loaded during Python startup but omitted from
the original 42-file archive. The old plan, raw native evidence and reports are
unchanged. `installed_operation_source_supplement_001/assessment.json` records
the current module hashes and matching bytes in the earlier full024 source
archive. That match is corroboration of current bytes, not proof of which
unpinned bytes executed in probe001 and not a retrospective pre-run freeze.
The result retains its native parity and timing evidence with a limited
42-file frozen-source claim; it does not have complete historical source
closure. The new original-map campaign follows both repository and `src/`
imports and also rejects actually loaded project modules absent from its pins.

Implementation:

- `scripts/experiments/g31_ics_circulation/probe_installed_operations.py`
- `scripts/experiments/g31_ics_circulation/verify_installed_operations.py`
- `scripts/experiments/g31_ics_circulation/business_update_outbox.py`
- `tests/test_g31_circulation_installed_operation_probe.py`
