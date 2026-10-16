# LT2 stronger fixed-route timing diagnostic — 2026-10-14

The finer fixed-initial-route reference reduced the observed gate6 comparison
from 1.41 to **1.401 seconds**, but did not certify stronger headroom. All 96
predeclared branches ran; 35 failed the inherited executable-action criteria and
remain unknown in the strict reference. No continuous timing optimum, online
solver, full B2/B3/B4 baseline, or complete-request 100ms claim follows.

The old 24-cell study and its inputs were left unchanged. The new native record
is [reference_timing_003](../../outputs/experiments/g31_ics_lt2_continued_20261014/reference_timing_003/receipt.json).
The read-only [independent diagnostics](../../outputs/experiments/g31_ics_lt2_continued_20261014/reference_timing_003/independent_diagnostics.json)
reassess every raw branch and preserve every denominator. The execution source
is [reference_reuse_timing.py](../../scripts/experiments/g31_ics_circulation/reference_reuse_timing.py);
the separate verifier is [assess_reference_reuse_timing.py](../../scripts/experiments/g31_ics_circulation/assess_reference_reuse_timing.py).

## Frozen comparison and information scope

Each gate0/6/12 keeps the old two trays, four offered jobs, topology, service
durations, capacity2/export-disabled node4, exact native checkpoint, owner views,
and complete continuation. Imported transport, later route rule, forecast rule,
return rule, 0.05s cadence, and 0.5s immutable retry behavior match the archived
old executable AST. The original route1/window1 incumbent is replayed exactly
in every gate. Protection remains each offered-job completion delta **<=0**,
without a numeric tolerance.

This is a **centralized offline reference**. Its candidate construction combines
public graph/service/headway data with owner A's lawful local `loaded_at` value
at the 0.11s checkpoint. That value is not delivered to owner B and must not be
used as a B-only online proposal input. Offline forks supply reference labels;
neither the candidate grid nor the imported continuation reads fork outcomes to
choose actions. Continuing owner decisions use local views and delivered
messages as before. No distributed-information equivalence is claimed for a
future online timing selector.

## Outcome-independent candidate construction

The [preregistered protocol](../../outputs/experiments/g31_ics_lt2_continued_20261014/reference_timing_003/preregistered_protocol.json)
and full 96-row unexecuted ledger were written before native branches. Every
gate has 31 fixed-initial-route timings plus one replay of initial route2 with
the old earliest window0. All four old departure windows are retained:
0.11, 2.21, 3.11, and 6.11 seconds.

Six additional public-duration centers are 1.1, 2.1, 2.2, 0.8, 1.9, and 2.4:

- Nominal loaded commitment on edge0→1, arrival at node1, and clearance of node1,
  derived from local `loaded_at=0.1`, service0=1, travel01=1, and service1=0.1.
- Nominal commitment and clearance shifted by the empty source-service plus
  travel51 lead, 0.1+0.2=0.3 seconds.
- Nominal clearance expanded by the public edge3→4 headway0.5, then shifted by
  that empty lead. This last center is a diagnostic seed, not an exact collision
  threshold.

Each center contributes the value itself and offsets ±0.001, where 0.001 is the
public 0.05s tick divided by50. This gives22 unique seeds. Nine deterministic
longest-interval midpoint refinements give31 timings. The rule, tie break, and
all intervals were fixed without evaluating outcomes. The offset is not a
protection tolerance.

The command is issued at checkpoint0.11 with message delay0.01. Earliest
departure, source grant, target reservation, and physical arrival are distinct;
these arithmetic seeds do not imply a lawful reservation or successful route.
Native validation remains authoritative. Coverage is finite within [0.11,6.11];
outside that interval, and between sampled timings, optimum and dominance remain
unknown.

## Complete results and unknown diagnosis

All96 branches reached H40, passed the physical receipt audit, and retained two
actual L returns followed by two L reloads. All selected ACKs reached a delivered
terminal status. There were no censored native horizons or unresolved selected
ACKs. Of384 offered job-branch records,354 completed; the30 incomplete receiver
records remain in the denominator.

| Gate | Assessed executable | Initial supply rejected `receiving_full` | Declared keep3/no-op, actual next8 | Strict full reference |
|---|---:|---:|---:|---|
| 0 | 20 | 10 | 2 | unknown |
| 6 | 19 | 10 | 3 | unknown |
| 12 | 22 | 10 | 0 | unknown |
| Total | 61 | 30 | 5 | 35 unresolved under the strict action contract |

The30 receiving-full rows use ten timings from1.101 through2.2 in every gate.
Each initial transfer receives an actual delivered `rejected/receiving_full`
ACK. The receiver job stays incomplete, while the other three jobs finish.
This proves failure of those selected immutable transfer intents under this
continuation; it does not prove that every possible resubmission or policy at
that time is infeasible. They remain
`unknown_incomplete_or_unexecuted` in the inherited assessor, with a separate
explicit rejection diagnosis. No row is excluded to produce a minimum.

The remaining five rows complete all four jobs and all three transfers, but
the inherited later rule records `next=3` as a no-op while the actual reuse1 edge
is7→8. These occur at departures3.485/3.86 in gate0 and4.985/5.36/5.735 in gate6.
There is no route command to node3 in those choices, so an `updated` ACK to3
cannot establish the intended action. The strict edge-match guard correctly
rejects the interpretation; physical feasibility alone does not repair it.

## What remains of the previous comparison

Among the successfully assessed protected fixed-route cells, departure2.201
beats old window2.21 by0.009s for the receiver at gates0/6, with the other three
job completions exactly unchanged. At gate6:

| Job | Finer fixed-route observed cell | Replayed initial route2/window0 | Difference |
|---|---:|---:|---:|
| loaded | 6.80 | 6.80 | 0 |
| receiver | 8.001 | 6.60 | -1.401 |
| reuse1 | 12.22 | 12.22 | 0 |
| reuse2 | 17.67 | 17.67 | 0 |

Thus the old 1.41 contrast did not disappear among assessed protected cells; it
decreased to1.401. Because unknown rows remain, this is an observed pairwise
comparison, not the best of a certified complete stronger reference. All three
named stronger finite minima remain null.

The negative gates remain: at gate0 the route2 challenger violates protection
for loaded/reuse1/reuse2; at gate12 the fixed route at0.11 already beats that
challenger by0.68s. Adding the replayed challenger gives zero observed protected
gain in those regimes. This does not replace or rewrite the old24-cell result.

## Necessary next correction and validation

The no-op mismatch requires an explicitly versioned continuation repair: when
the rule requests node3 and the current native route is not node3, submit a
real route3 request, require its delivered native ACK, and verify the actual
edge. The policy also needs an explicit response to terminal receiving-full
rejection if it is expected to continue serving that receiver. Neither change
is a harmless wrapper or expiry repair; both change the common continuation.
First replay and compare every old24 cell under such a version2 protocol, then
preregister a new stronger reference. No extra native branches were used here.

The native artifact remains016, SHA256
`af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0`.
One worker finished the96 branches in30.873s, inside the60s subprocess limit,
with `source_changed=[]`. Aggregate runtime is not request-latency evidence.

Attempt001 stopped before native loading on a JSON tuple/list preflight
comparison; attempt002 stopped after checkpoint creation, before any fork,
on the same representation issue in the lawful views. Both records remain.
Comparisons now normalize JSON structure while preserving exact native hashes.
Total executed branches across all three attempts are96.

The [20-test receipt](../../outputs/experiments/g31_ics_lt2_continued_20261014/reference_timing_tests_001.xml)
covers outcome-independent construction, all-gate denominator, exact action
mapping, duplicate-incumbent rejection, incomplete/failed/nonfinite evidence,
strict1e-12 regression rejection, terminal-ACK diagnosis, and saved reassessment
of all96 branches. The verifier also checks immutable retries, delivered-before-
decision messages, identical old inputs/checkpoints, submitted departure times,
source archives, and unchanged strict regime reports.

Execution commands and source identities are recorded in the receipts.
Read-only verification can be repeated with `PYTHONPATH=src;.` and:

```text
python -m scripts.experiments.g31_ics_circulation.assess_reference_reuse_timing --evidence outputs/experiments/g31_ics_lt2_continued_20261014/reference_timing_003 --output NEW_DIAGNOSTIC_JSON
```

Saved-evidence tests additionally set
`G31_TIMING_REFERENCE_EVIDENCE=outputs/experiments/g31_ics_lt2_continued_20261014/reference_timing_003`
and run `python -m pytest tests/test_g31_circulation_reference_reuse_timing.py -q`.
