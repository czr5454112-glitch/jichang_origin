# Fixed 512-row original-bridge diagnostic, 2026-10-17

## Decision

The single executed run, `bridge_prefix512_002`, is **unknown**, not a passed saved-replay gate. Its original-policy prefix reached the planned censor before row 513, but its original C exit dependency check did not finish within the unchanged 120-second outer budget. No retry, budget extension, native simulation, full saved acceptance, or 2x performance claim follows from this run.

`bridge_prefix512_001` is a prepared, unexecuted directory. Preflight caught selection of the build environment rather than `python_startup_environment`; the correction and an eighth unit test preceded the only launch, `002`. The original directories and receipts remain intact.

## Actual execution

- Runner: `audit/review_20261017/profile_bridge_prefix512.py`; focused tests: `test_profile_bridge_prefix512.py`, eight passed before execution.
- Source: the existing bcdm2 original-bridge design and frozen plan, exact input, new 37,270-row manifest, old 27,218-row manifest, and bootstrap manifest. Exactly rows 0 through 511 were selected and hashed; no raw-final or unselected-row payload was read.
- Original C `begin` and `finish` were retained. The admitted startup environment was retained. The original policy and module globals were unchanged, with private actor state and the original observed tape/owner implementation.
- The observed implementation's unavailable future supply boundary and final cap IDs were **not guessed**. The scope permits only the strictly compared initial bootstrap prefix before such boundaries. Encountering a supply, cap, or relay boundary would make the run unknown. None was encountered in this prefix.
- Row 513 raises a dedicated `BaseException`, so the policy's ordinary error handling cannot turn censoring into successful completion.
- External Windows Job ownership limited the only child. `external_wall.json` records hard timeout at 120 seconds and whole wrapper duration 120.0199325 seconds, including final cleanup. A process exit-code field of zero does not override the recorded hard-timeout status or the missing C exit proof.
- `C_entry.json` exists; `worker_partial.json` says `prefix_closed_C_exit_pending` and `C_exit: null`. No completed `worker.json` or `C_exit.json` exists.

## Measured stages

| Stage | Seconds | Interpretation |
|---|---:|---|
| Entry source and selected input checks | 0.5125126 | Completed |
| Original C entry full dependency checks | 72.8914350 | Completed, unchanged check |
| Fixed prefix stage | 14.1884522 | Completed censor; includes replay preparation and output |
| Instrumented policy prefix | 13.7456431 | 512 new rows and 512 old rows strictly compared |
| Original C exit full dependency checks | Not closed | Started before timeout; no success inference |
| Whole bounded execution | 120.0199325 | Unknown, hard timeout |

The prefix covers physical time through 500 seconds, 101 completed activation spans, and one interrupted activation span. These are a diagnostic saved prefix, not an execution of the full physical input.

| Instrumented scope | Calls | Inclusive seconds | Exclusive seconds |
|---|---:|---:|---:|
| Outer observer with endpoint | 512 | 12.4444757 | 10.0675686 |
| Client refresh | 102 | 3.0072935 | 1.1504945 |
| Ordered old-prefix comparison | 512 | 1.1247150 | 0.0431010 |
| Reference gzip and decode | 1,024 | 0.9443761 | 0.9443761 |
| Gzip and first decode | 512 | 0.5202040 | 0.5202040 |
| File hash | 1,024 | 0.4896994 | 0.4718841 |
| Ordered semantic encoding | 1,024 | 0.3795266 | 0.3795266 |
| Complete digest | 99 | 0.0147113 | 0.0025834 |
| C typed bytes attempt | 99 | 0.0063203 | 0.0063203 |
| Candidate identity | 99 | 0.0038608 | 0.0038608 |

All 99 digest outcomes returned a digest with one C attempt each and no fallback-writer call. The raw conservative classification label remains `direct_C_or_exception`; its paired `outcome: returned_digest` disambiguates these actual calls. No later-history full-capture/possession path was observed in this short prefix.

## Limits and next action

The profiler uses external `sys.setprofile` instrumentation. Its inclusive scopes nest, so they must not be added. These times are **not uninstrumented speed**, CPU time, or a full-day estimate. The observer's exclusive residue includes unclassified observer work, copying/encoding, and profiling overhead; it is not a proven single-function bottleneck. The same restriction applies to comparison with any separately instrumented ABBA run.

The structural conclusion is that this prefix does not justify further digest micro-optimization as the remedy for the original bridge's total cost: the 99 digests occupy 0.0147 instrumented seconds while a single unchanged C entry check occupies 72.89 seconds. Investigate dependency verification lifecycle and observer duplication while preserving both original entry/exit evidence obligations; do not merely omit checks, relabel this run as success, or run the 600-second full replay again. Full C exit closure and later boundary coverage remain unproved.

Raw evidence is under `audit/review_20261017/bridge_prefix512_002`: `external_wall.json`, `progress.jsonl`, `profile.json`, `profile_partial.json`, `worker_partial.json`, `C_entry.json`, and `plan.json`.
