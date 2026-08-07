# G4IRSF18 native learned merge runtime

## Outcome

The frozen J7 affine artifact now runs inside the destination-local E4/J2
merge controller. It scores only the already legal exact-slot JIT candidate
set; it does not add a route search, future schedule input, global scan, or a
new reservation rule. J2 remains the authoritative fallback.

The current artifact remains a fixed-workload research candidate. Its
artifact flag `production_closed_loop_authorized` is false, and an artifact
cannot self-promote. Production ownership additionally requires an artifact
production flag, an independent runtime production grant, and an offline gate.

## Frozen inference contract

- Schema: `czr005.g4irsf18.teacher_counterfactual_linear_merge.v1`
- Family: `teacher_warm_start_counterfactual_advantage_affine`
- Feature contract: `MERGE_TRACE_LOCAL_V1`, exactly 18 ordered local features
- Inference: `score = bias + sum(weights[i] * ((clip(x[i])-mean[i])/scale[i]))`
- Direction: higher score wins
- Candidate set: current destination-local legal exact-slot JIT set, 2..16
- Non-finite, out-of-contract, or candidate-count OOD: J2 fallback
- 120-second starvation band: authoritative pre-model J2 guard
- FIFO fallback: only finite, in-contract equal-score ties within `1e-12`

The runtime validates schema, family, feature order, normalization dimensions,
bounds, authorization label, identity/outcome exclusions, OOD fallback, tie
scope, and starvation threshold. A semantic artifact mismatch is observable as
`INVALID_ARTIFACT_J2_FALLBACK`; it is not converted into an online exception.

## Exact wrapper kwargs

```python
merge_grant_timing_mode="jit_fair_aging_deadline",
g4irsf18_merge_policy_mode="research_closed_loop",
g4irsf18_merge_policy_artifact=(
    "artifacts/models/g4irsf18_j7_teacher_cf_affine.json"
),
g4irsf18_merge_research_closed_loop_authorized=True,
g4irsf18_merge_fixed_research_workload=True,
g4irsf18_merge_production_closed_loop_authorized=False,
g4irsf18_merge_offline_gate_passed=False,
g4irsf18_merge_coverage_cap=0.05,
g4irsf18_merge_max_overrides_per_segment=2,
g4irsf18_merge_kill_switch=False,
```

The reusable arm is
`artifacts/manifests/g4irsf18_j7_native_research_arm.json`. It fixes the first
research workload to the protected 144-segment canonical-map prefix and keeps
production authorization false.

## One real 144-segment command

After generating the plan once with the explicit research arm, the real job is:

```powershell
python scripts/eval/run_g4irsf18_system_campaign.py run --plan artifacts/manifests/g4irsf18_j7_native_research_plan.json --binary <ABSOLUTE_PATH_TO_czr005_cpp.pyd> --results-dir outputs/runtime/g4irsf18_j7_native_research --stage ladder --only-job j7_teacher_cf_affine_research_5pct__s144 --force
```

The plan-generation command is:

```powershell
python scripts/eval/run_g4irsf18_system_campaign.py plan --learned-arm artifacts/manifests/g4irsf18_j7_native_research_arm.json --output artifacts/manifests/g4irsf18_j7_native_research_plan.json
```

## Telemetry semantics

The counters intentionally separate mechanism exposure from action change:

- `model_opportunity_count`: every legal JIT service opportunity, including a singleton.
- `model_eligible_count`: opportunities with at least two legal candidates.
- `model_proposal_count`: finite, in-contract affine evaluations that produced a proposal.
- `model_applied_count`: proposals that passed every runtime gate.
- `model_ownership_count`: applied decisions owned by the model, including the same action as J2.
- `distinct_action_mutation_count`: applied decisions whose action differs from J2.
- `*_fallback_count`: J2, tie-FIFO, shadow, authorization, coverage, segment cap, starvation, and kill-switch reasons remain separate.

Every stored candidate row contains the exact 18D feature vector, native affine
score, J2 baseline ID, proposal ID, final chosen ID, mode, reason, OOD/invalid
state, and proposed/applied/chosen booleans.

## Evidence

Native and binding evidence completed in this implementation:

- MSVC focused native target compiled and passed.
- Pybind module compiled with the append-only ABI tail.
- C++ tests cover exact 18D row reconstruction and score parity, real research
  ownership, an observable action mutation, shadow behavior, invalid/OOD to J2,
  zero coverage, zero segment overrides, score tie to FIFO, production
  fail-closed, explicit kill switch, fault generation repair, and grant safety.
- Python wrapper tests cover the exact 80-argument append-only call, path/mapping
  artifact input, semantic-invalid pass-through to native J2 fallback, hook
  restrictions, runtime-control typing, and the explicit research arm.
- Canonical-map shadow parity with the frozen J7 artifact had 18 features and
  absolute native/Python affine score error `3.44e-15`; it proposed once,
  applied zero actions, and preserved J2.
- A bounded canonical-map research smoke with full test coverage authorization
  recorded `eligible=1`, `proposal=1`, `applied=1`, `ownership=1`, and
  `distinct mutation=0`, with zero reservation/fault-entry violations. This is
  an interface/ownership smoke only, not a ladder conclusion.
- The actual fixed 144-segment arm at the default 5% cap completed all 144
  segments with hard safety pass, zero conflicts, zero unsafe fault entries,
  and no full A*. It recorded `opportunity=442`, `eligible=0`, `proposal=0`,
  `applied=0`, `ownership=0`, and `distinct mutation=0`. Therefore this rung
  did not exercise learned ownership and must not be reported as a learned
  performance result.

The persisted result is
`outputs/runtime/g4irsf18_j7_native_research/j7_teacher_cf_affine_research_5pct__s144.json`.

After the CPython 3.11 native module was relinked, the final predeclared
14-job learned closed-loop integration ladder completed. The 2048-segment 5%,
25%, 50%, 80%, and 100% coverage arms recorded respectively 6, 34, 69, 109,
and 137 applied/owned model decisions. Distinct action mutations were 0, 1,
1, 3, and 3. At 8,192 segments and 100% coverage, 935 eligible opportunities
produced 919 applied/owned decisions, 44 feature-distinct mutations, and 16 J2
fallbacks, all from the authoritative starvation guard. At the 43,603-segment
capacity rung, 3,526 eligible opportunities produced 3,500 applied/owned
decisions, 154 mutations, and 26 starvation fallbacks. Every hard-safety and
native-contract gate passed; invalid, OOD, authorization, kill-switch, tie,
coverage, and override fallbacks remained zero.

This closes the native mechanism-exercise gap: the seam demonstrably owns
normal-flow decisions and changes the J2 action. It does not establish a
production win. The matched 43,603 result changed mean TTH by -0.004653 s,
left p95/p99 unchanged, and added 228 events. The authoritative outcome and
authorization record is the final 14/14 learned closed-loop report and JSON,
not the earlier 144-segment interface smoke.

## Follow-up idea from the evidence

The 144 prefix proves safe non-interference but contains no multi-candidate
opportunity. A research ladder should predeclare a minimum eligible-opportunity
threshold and mark any rung below it `MECHANISM_NOT_EXERCISED`. At 5% cumulative
coverage the first model action cannot occur before the 20th eligible decision,
so larger fixed prefixes should be selected from prior J2 telemetry rather than
loosening safety, synthesizing contention, or raising coverage after seeing the
result. Performance comparison should begin only after eligibility, ownership,
and distinct mutation are all non-zero on a predeclared workload.

The final ladder also shows that uniform ownership is wasteful: 3,500 full-run
model decisions yielded only 154 feature-distinct actions. A follow-up research
arm should first predict whether a local opportunity can change J2 and spend
the same bounded ownership budget on those opportunities. That mutation gate
must remain shadow-first and retain the current starvation guard, J2 fallback,
per-segment cap, kill switch, and event-cost accounting.
