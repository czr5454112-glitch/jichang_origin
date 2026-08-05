# G4IRSF16 new ideas and evidence

This log separates verified implementation changes from hypotheses for the next round. It is not a claim that every idea improved full-scale TTH.

## 1. Runtime-realizable feature contracts

**Verified change.** The first model schema contained `downstream_pressure` and `has_physical_fault`, but the frozen native decision trace exposes no equivalent local scalars. Substituting a shield flag, a risk flag, or zero would have fabricated deployment inputs. Both fields were removed from learning: the model now has 29 ID-free fields, including 10 dynamic fields observed on 2,172/2,172 formal targets. Physical fault remains an authoritative supervisor/physical-shield state.

**General lesson.** A feature is deployable only if its training value and native decision-time value share one exact semantic definition. “Similar proxy” is not enough for a safety gate.

## 2. Hard-component splits without giant-component collapse

**Verified change.** Clone and directly affected task relationships remain hard union edges. Coarse source/time/node/kind fields are balance diagnostics rather than union edges because literal unioning collapses most of the 2,172-row panel into a giant component and makes a four-way split impossible. Pure component hashing produced 1,332/318/314/208 train/calibration/validation/final-audit rows while retaining zero hard-component overlap.

**General lesson.** Decentralized decisions share broad contexts; treating every shared context as identity destroys evaluation support. Leakage prevention needs causal identity edges, while context belongs in held-out diagnostics.

## 3. Platform-independent tiny-model fitting

**Verified change.** Windows twice raised an uncatchable `0xc06d007f` native exception in compiled sklearn/SciPy solver paths. The G4IRSF16 linear heads now use deterministic full-batch elementwise logistic optimization, elementwise Platt fitting, and cyclic coordinate-descent ridge. The scientific model family is unchanged, model-contract tests pass, and the real 2,172-row training pass completes normally without loading BLAS/OpenMP solver paths.

**General lesson.** For a 29-feature safety model, a small auditable optimizer is preferable to an opaque native dependency when both produce the same intended model class and the native dependency is operationally unstable.

## 4. Causal support says “abstain,” not “tune harder”

**Verified evidence.** The selectable train/calibration/validation partitions contain only 19 beneficial I3 rows (13/3/3), below the preregistered 24/6/6 pre-audit minima. I3 is therefore risk-veto-only and no multi-alternative/listwise campaign was launched. I4 has only 20 selectable positives (14/3/3), below its 24-row support gate; the four final-audit positives remain sealed and cannot authorize training. D0 is retained only as a deterministic support/validation diagnostic. It proposed no validation activation under benefit LCB, harmful UCB, utility LCB, and OOD abstention. The formal result is `CAUSAL_LEARNING_MODEL_NO_GO`.

**Next-round hypothesis.** The next useful causal question is not another threshold sweep over I3/I4. Evidence should move to source ordering (I1) or destination service-token semantics (G2), provided their causal concentration gates pass.

## 5. Sparse externality is a tail problem

**Verified evidence.** The 232 selectable H_system pairs contain 131 nonempty external sets; one action can affect as many as 365 other segments. Maximum positive other-bag harm is 78.1001 s and maximum CVaR95 is 54.036885 s, while extra deadline-miss labels are identically zero. Final-audit tail outcomes are excluded. The small externality head has validation ECE about 0.1933 and is diagnostic-only; the preregistered B1 CVaR95 threshold is metadata, not a passed gate, because no calibrated CVaR upper-bound head is supportable here.

**Next-round hypothesis.** Target at most 512 new H_system pairs at high-benefit/high-risk/high-uncertainty states. Do not rerun the full 64-shard campaign, and do not train a deadline-miss head until the target is non-degenerate.

## 6. Mechanism-matched controls are mandatory

**Verified boundary.** G4IRSF15 labels and G4IRSF16 traces use E4 destination-merge-request semantics, while the historical F2/v2-safe headline values use E0. A candidate must first be compared with a fresh E4 supervisor-off control. Cross-mechanism numbers may be reported as context, not as a strict algorithmic win.

## 7. Full native shadow before action

**Verified evidence.** The frozen E4/M0 trace completed all 43,603 segments and 28,506 bags, captured 522,871 decision rows, matched all 2,172 formal targets, and passed four independent replay/union hard gates with zero failed, conflict, unsafe, A*/CIE, global-scan, future-route, or unresolved-deadlock result. Full 1x shadow scored all 522,871 rows: I4 had 520,338 eligible states, 0 proposals, 4,149 OOD abstentions, and 2,533 states outside its causal action domain; I3 had 119,407 opportunities and 0 authorized proposals. A streaming row-level validator confirmed zero feature-contract violations, illegal proposals, or F2 action mutations.

**General lesson.** Shadow OOD rate is itself learnability evidence. It should guide a bounded targeted campaign, not be suppressed by silently widening features or disabling abstention.

## 8. Neutral-action canary for runtime plumbing

**Verified offline evidence.** The ID-free H5 rule (`F2 margin <= 1.518316644839415`, target scheduled incoming >= 5, target queue >= 0) activated 10/164 validation rows; all ten were causally neutral and none harmful, but it had no positive utility. It is therefore not a promoted policy.

**Implementation use only.** H5 is reserved as an `8192_DIAGNOSTIC_ONLY_NOT_PROMOTED` closed-loop canary to exercise a real one-natural-opportunity hold, latches, native telemetry, and matched E4 control. It must not be described as a learned or performance-improving candidate.

## 9. The performance denominator must survive protected-segment expansion

**Verified change.** Per-segment `finish_time - release_time` remains useful for paired diagnostics, but it is not the formal raw-bag TTH denominator. The closed-loop runner now aggregates every protected segment by raw `task_id`, reconstructs original-entry TTH from scheduled pre-release dwell plus source wait plus network time, and reports candidate/off mean, p95, p99, source-wait, and network-time deltas. The early tail gates are evaluated on that raw-bag denominator: p95 must be no more than off +2 s and p99 no more than off +4 s.

**Verified evidence.** Real native closed-loop runs changed 19 actions at 144 segments, 102 at 512, 515 at 2,048, and 1,865 at 8,192. The raw-bag p95 and p99 deltas were 0 s at all four ladders; at 8,192 the mean delta was +0.001517 minutes, or about **+0.0910 s per raw bag**. Source wait increased by about 0.1496 s while network time fell by about 0.0585 s. This is successful safety/plumbing evidence for a diagnostic canary and negative performance evidence against promoting it.

## 10. Bounded audit telemetry is not a live safety invariant

**Verified evidence.** At 2,048 segments, the bounded merge-lifecycle log dropped 2,179 candidate and 2,175 off records after preserving its configured storage bound. At 8,192 it dropped 100,604 candidate and 100,782 off records. That made the aggregate `merge_grant_protocol_integrity_pass` flag false because the flag also encodes complete lifecycle telemetry. Both executions nevertheless retained live conservation, active-grant bijection, exact-slot semantics, zero final unconsumed grants, zero outstanding requests, and zero stale arbitration. The 8,192 candidate had 1,230 post-commit rollbacks and the off control had 1,231; these exactly matched their respective queue-capacity block counts and are the legal compensation path, not a violation.

**Verified change.** Closed-loop safety gates now test the live state invariants directly and require post-commit rollback to equal the queue-capacity block count. Lifecycle drops are reported explicitly as telemetry truncation and do not masquerade as an unsafe execution.

**General lesson.** A decentralized large-scale runtime needs bounded observability. Correctness should be decided from live conservation and violation counters; completeness of a capped diagnostic log is a separate evidence-quality property.

## 11. Integrity is not promotion authority

**Verified change.** A self-consistent artifact SHA proves only that bytes were not accidentally changed. It does not prove that a policy passed scientific promotion. Learned-model closed loop is now rejected centrally in native configuration while the offline gate is no-go; shadow remains diagnostic-only and reports `promotion_authorized=false`. Python wrappers enforce the same rule, so direct pybind use cannot bypass the decision gate.

**General lesson.** Decentralized executors need two independent capabilities: immutable artifact identity and an explicit promotion authorization rooted in the offline decision artifact.

## 12. Fault generations must be monotonic even when priority boosts clear

**Verified change.** The supervisor no longer reuses the temporary `fault_priority_generation`, which legitimately resets after repair. It receives a separate monotonic physical-fault generation, rejects truly stale decisions, and enforces `FaultHold`/`SafeHold` by clearing the selected edge before commit. Native fault/repair and authorization regressions pass.

**General lesson.** Recovery priority is transient policy state; physical fault generation is causal identity. Conflating them can permanently suppress a repaired bag or let a fail-closed decision leak through integration.

## 13. Actionable pivot and deferred oracle claims

**Verified decision.** `CAUSAL_LEARNING_NO_GO_WITH_ACTIONABLE_PIVOT` is binding for this round. The all-state/top-coverage/risk-constrained outcome oracles are descriptive upper bounds. Separate held-out-source, held-out-time, and no-node-ID generalization oracles were not estimated after the pre-audit support gate failed; they are recorded as `NOT_EVALUATED_SUPPORT_NO_GO`, not silently treated as passes.

**Next-round priority.** Start with the bounded I1 source-front ordering pilot (64 to 128 opportunities) using a generation-bound capability tied to release time, source-queue generation, priority snapshot, owner, atomic consume, and stale/forged rejection. The 8,192 H5 result shows that additional local holds mainly shift wait and worsen mean. Keep G2 destination service tokens gated until causal clustering proves merge/service timing concentration (the preregistered >=50% condition or equivalent direct evidence). Expansion remains closed.

## 14. Historical evidence must bind repository bytes or canonical text

**Verified portability finding.** The sealed G4IRSF15 descriptor manifest bound raw bytes from its generation-time Windows working tree. Eight of 14 bound source files therefore contain CRLF in the historical identity, and three contain a mixed CRLF/LF representation left by incremental edits. Its 29,121,147-byte offline sampling CSV is likewise bound in CRLF while the sealed Git blob is LF. After LF normalization, every affected historical working-tree file is byte-identical to its sealed Git blob; no semantic source or sampling-input drift exists. A fresh Linux checkout nevertheless cannot satisfy the raw host-byte hashes without reconstruction.

**Verified compatibility change.** Successor CI now reconstructs only the sealed EOL representation inside a disposable G4IRSF15 worktree. The compatibility helper pins the historical seal commit, source-bundle identity, and offline-sampling binding; rejects path escape, bare CR, and non-EOL changes; proves normalized content unchanged; and then requires every historical byte count and SHA-256 to match exactly before the independent G4IRSF15 validator runs. This does not relax a source gate or alter the current runtime. A fresh LF-only seal simulation passed the original 747,962-row descriptor scan after reconstruction.

**General lesson.** Future evidence should bind Git blob identities for source provenance, or explicitly canonicalize text before hashing. Raw host working-tree hashes are appropriate only when the host representation is itself committed or otherwise reproducible.
