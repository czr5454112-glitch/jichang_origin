# A3 FQI independent audit and selection-only amendment — 2026-10-19

## Actual frozen evidence

The independently executed standard-library audit is preserved under
`outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/A3_fqi_independent_audit_001/`
as `audit.py` and `report.json`. Run the audit from the worktree root with Python.
It imports no NumPy, Torch, native controller, or training implementation.
The public feature functions are extracted from the exact archived source; matrix
forward propagation, rewards, Monte Carlo returns, and FQI targets are independently recomputed.

The audit passed all 18 checkpoints, 162 training targets, 36 actual event-reward
intervals, train-only normalization, gamma 1, model/file/content hashes, training
curves, and original development metrics. All 129 training-attempt source archives
and its completed outer receipt were verified. Historical sources are checked
against the archived bytes, not today's mutable native-controller files.

Original training `A3_fqi_training_001`, collection contract 003, all collection
episodes, all iteration files, and the original selected checkpoints remain unchanged.
The original rule chose iteration 0 for seeds 17, 29, and 43. These selected models
are Monte Carlo initialization models; they must not be described as FQI-selected
policies. This audit ran zero fits and zero native branches and read no held-out case.

## Why the old metric structurally favors the initial behavior value

The same legal actor feature/action vector appears with different Monte Carlo
targets because later protected exploration chooses different continuations.
The irreducible behavior-return MSE for these repeated feature vectors is
28.0017403 on train and 28.5171292 on development. The initial checkpoint approaches
that floor. FQI instead learns the maximum over supported legal continuations.
A rise in behavior-return MSE therefore does not by itself establish FQI divergence.

For example, one identical development state/action has observed behavior returns
-46.240, -67.318, and -50.719. Its deterministic immediate reward and successor are
identical; the future behavior differs. The closed empirical supported graph gives
-46.240 as its supported optimal continuation target. All six distinct development
state/action groups have deterministic reward, termination, and successor;
the nine original development rows are retained with equal weight.

Diagnostic supported-graph MSE, already inspected before this amendment:

| Seed | Iteration 0 | Diagnostic minimum | Iteration |
|---|---:|---:|---:|
| 17 | 24.200720 | 0.030272 | 5 |
| 29 | 23.963891 | 0.018718 | 2 |
| 43 | 24.249367 | 0.016860 | 2 |

These numbers are diagnostics from existing weights, not the result of a registered
selection-only job. The new launcher job must produce its own receipt and original-byte
copies. The amendment is explicitly post-development inspection, before formal
held-out evaluation; it is not described as the initial preregistration.
Bellman residual was also audited diagnostically but is not a second selection criterion.

## Frozen selector contract

New module: `scripts/experiments/g31_ics_circulation/foundation_fqi_checkpoint_selection.py`.

Pure functions `supported_empirical_targets`, `forward`, and `choose` validate and
evaluate the original development rows. State identity matches frozen FQI support
and removes only episode ID, decision ID, and opportunity metadata. Semantic
action identity is exact; a disabled selected alias cannot borrow another alias's
admission. Every nonterminal has an exact actual same-source successor and a
strictly increasing clock. The graph rejects inconsistent reward/successor/support,
missing actual support, cycles, truncation, nonfinite values, or test rows.

The sole replacement criterion is
`minimum_development_supported_empirical_optimal_mse_then_earliest_iteration`.
It retains the original nine-row equal weighting, all three seeds, and all six
iterations per seed. Iteration 0 remains eligible. This is optimal only within
the observed legal development graph, not a global optimality claim.

`make_plan(training_directory, training_registration_path, addendum_path)` returns
a plan. It verifies original training/collection archives, the outer training
receipt, copied training-plan bytes, collection contract, source pins, and artifact
paths before constructing complete immutable references. The root launcher registers
the addendum and plan. The CLI requires exact stdin admission
`g31_fqi_checkpoint_selection_v1` before any plan read:

```
python -m scripts.experiments.g31_ics_circulation.foundation_fqi_checkpoint_selection --plan PLAN --output NEW_DIRECTORY
```

The suggested outer hard budget is 180 seconds, CPU only, zero fits and zero native
branches. The root launcher owns execution. Selected files are copied verbatim from
the old iteration checkpoint, with matching SHA-256. Output includes all 18 metrics,
the empirical graph and per-row targets, the complete reference/pin chain, selected
file references, and a receipt reporting no fitting/native/held-out evaluation.
A new output directory is mandatory. Model architecture, weights, feature source,
rewards, gamma, collection data, and original results are unchanged.

## Interpretation limits

The development set is a small deterministic mechanism case already used for
diagnosis and selection. This correction does not establish held-out improvement,
generalization, a calibrated value function, or native benefit. Each selected seed
still requires the preregistered guarded native-consumption/evaluation chain.
Guard authority remains separate from model ranking.

## Completed registered selection and later API hardening

The root launcher subsequently executed `A3_fqi_selection_002` in 11.156 seconds
outer wall time, with source-exit pins unchanged. The actual selected checkpoints
are seed 17 iteration 5, seed 29 iteration 2, and seed 43 iteration 2, with development
supported-graph MSE 0.0302717321, 0.0187178955, and 0.0168595978, respectively.
The independent standard-library post-selection audit is saved in
`cycle_001/A3_fqi_selection_review_001/audit_selection.py` and `report.json`.
It verifies all 18 forwards/metrics, the exact closed nine-row development graph,
the completed outer receipt and archived source, all input references, and byte-for-byte
equality between each selected copy and its existing iteration checkpoint. The
original three iteration-0 selected files remain unchanged. No held-out result was read.

The executed selector source SHA-256 is
`dd3cd6091ec9ab92e04f951234ed3c898e7e3a0fb85e50de772d9d0b93e7ddcf`;
its archived bytes remain authoritative for this run. After execution, one general
API hardening moved registration/output identity verification before reading the
requested training directory. A wrong directory is now rejected before any result
read there. The actual registered invocation already supplied exactly the correct
closed training directory, as independently verified. This later change affects
neither the criterion, weights, metrics, nor selected files; no reselection was run.
The hardened API has 32 passing pure fixture regressions.

