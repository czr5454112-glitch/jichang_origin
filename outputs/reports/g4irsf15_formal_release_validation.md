# G4IRSF15 formal release validation

- Validation time: `2026-08-04T23:07:30+08:00`
- Status: `PASS_CAUSAL_GATE_VALID`
- Causal labels: `2172`
- Complete by kind: `I3=1086`, `I4=1086`
- Complete H_system pairs: `256`
- Learning authorized: `true`

The publication-portable validation command was:

```powershell
C:\Users\38908\.conda\envs\czr005\python.exe scripts\validate_g4irsf15_formal_release.py --root C:\tmp\czr005_g4irsf15_worktree --scope formal
```

It delegates to the frozen independent validator and does not rebuild the
native extension, rerun the descriptor scan, rerun pilot/formal workers, or
read the 2.45 GiB ephemeral runstate. It independently verifies the frozen
source/build/plan chain, all 489 compact evidence blobs, 2172 labels, 256 dense
H_system reconstructions, split isolation, tables, report bindings, the formal
gate, and the complete 1000-replicate clone-group bootstrap analysis.

## Post-freeze compatibility boundary

The frozen validator is source-bound at SHA-256
`7e43047065f1d9ec253f2ecf1f0c562af51e849e13749120d3df6516cfdf5615`
inside source bundle
`38f4ab3dc4cf45b67499e1da0e46208c63e55288f32fb9ae5f877c168172a7a5`.
It was not edited because doing so would invalidate the full campaign chain.
The separate release entry point applies only two in-memory, fail-closed
contract reconciliations:

1. A formal plan correctly has `pilot_round=null`; the frozen collector calls
   `int(null)` even though the formal compact namespace ignores the round. The
   adapter accepts only the exact formal schema/campaign/null-round tuple and
   supplies a path-only sentinel on a shallow copy. Published formal evidence
   must still contain `pilot_round=null`.
2. The generator and the independent dense sidecar validator permit an empty
   realized-outcome set, and compact projection publishes its exact length.
   Six eligible I4/H_system labels therefore correctly bind `row_count=0` and
   the typed empty-sidecar hash
   `61090c80331138c49fbbfe5abbd96003ad002529606c7225b53df74d05c099d3`.
   The frozen label validator alone requires a minimum of one. The adapter is
   limited to those exact, independently rederived, zero-change cohort rows;
   the original unmodified label still passes the frozen label-hash and every
   other semantic check.

The adapter restores every temporary function binding in `finally`. Focused
compatibility regression tests passed `10/10`; a lightweight pass validated
all `2172/2172` labels (only six used the empty-set path), and the split plus
weighted-effect post-collect preflight passed before the final full validation.

These corrections change no artifact bytes, sampling decisions, labels,
effects, or gate thresholds. The next campaign should incorporate explicit
formal/pilot and zero-cardinality branches into its newly frozen validator and
then regenerate its own source-bound chain.
