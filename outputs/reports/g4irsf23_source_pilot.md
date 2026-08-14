# G4IRSF23 targeted Source pilot

## Decision

`TARGETED_SOURCE_NO_SUPPORT` and `SOURCE_ADMISSION_SELECTOR_NO_GO`.

The new native Source action is real, local, deterministic, and safe. It is not a useful optimization lever under the preregistered 2x pilot. All 256 selected interventions changed exactly one immediate action, but none of the 176 full-system outcomes reached usable or strong promotion strength. The project therefore stops Source selector work and pivots to the existing local precursor Route seam; it does not add a larger model or a central planner.

## Evidence scope

The final audit passed the twenty ignored raw payloads through the existing strict `merge_pair_payloads` allow-list and target-join path:

- `h_system-000..007`: 8 payloads × 8 pairs = 64 H_system pairs.
- `h_system_resume14-000..007`: 8 payloads × 14 pairs = 112 H_system pairs.
- `h_bag-000..003`: 4 payloads × 20 pairs = 80 H_bag pairs.

This gives 256 executed targets over 256 unique Source groups, with zero duplicates, zero unexpected targets, and zero missing targets. The plan contains 432 horizon targets because every group has an H_bag target and 176 also have H_system. Execution intentionally avoids a redundant H_bag replay for those 176 groups: the H_system pair already contains the identical immediate-action certificate. Formal coverage is therefore 176 H_system + 80 remaining H_bag = 256 groups.

The H_system quota is complete: 128 block-7 and 48 block-8 pairs. All H_system runs use the protected full 2x workload of 57,012 raw bags / 87,206 segments.

## Exact action and safety audit

Every one of the 256 pairs satisfied the intended small contract:

| Check | Passed |
|---|---:|
| Same checkpoint state | 256 / 256 |
| Baseline `ADMIT_NOW` vs treatment `HOLD_ONE_NATURAL_OPPORTUNITY` | 256 / 256 |
| Exactly one changed action, same front bag | 256 / 256 |
| Exactly one observed HOLD opportunity | 256 / 256 |
| Forced A0 after HOLD; repeated HOLD count zero | 256 / 256 |
| Pre-action snapshots match; post-commit verified | 256 / 256 |
| Pair and requested horizon complete | 256 / 256 |
| Live safety, safety equivalence, and applicable hard gate | 256 / 256 |

The 176 H_system pairs also passed the terminal formal gate. In both baseline and treatment they completed all 87,206 segments with zero failed segments, unsafe entries, unresolved deadlocks, reservation conflicts, event limits, or time limits. They made zero runtime full-A* calls, global scans, future-route reads, future-schedule reads, or two-step reservations. Shared A0 terminal results were used for runtime economy only after equivalence against plain replay was verified in every H_system payload.

The other 80 pairs stop at H_bag, so a terminal full-system formal gate is not applicable to them; their local live-safety and horizon gates all pass. A false `formal_hard_gate_pass` default on those rows is therefore not counted as a failure.

## Causal effect

| Scope | H_system | Neutral | Weak diagnostic fair | Usable/strong fair | Harmful | Mean system delta (s) | Range (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| All | 176 | 173 | 3 | 0 | 0 | -0.000082139 | [-0.004837473, +0.000007770] |
| Block 7 | 128 | 125 | 3 | 0 | 0 | -0.000113409 | [-0.004837473, +0.000000140] |
| Block 8 | 48 | 48 | 0 | 0 | 0 | +0.000001249 | [0, +0.000007770] |

The same 176 completed H_system branches also expose the mean-time decomposition below. Every value is treatment minus baseline in seconds per complete raw bag; it is descriptive evidence and does not add a gate.

| Scope | Component | Min | Mean | Median | Max |
|---|---|---:|---:|---:|---:|
| All | Source wait | -5.698800252e-05 | -8.921566614e-07 | +1.754017598e-08 | +1.648775823e-06 |
| All | Network time | -4.780502350e-03 | -8.124665139e-05 | -1.754015599e-08 | +7.752754705e-06 |
| All | Scheduled pre-release wait | 0 | 0 | 0 | 0 |
| Block 7 | Source wait | -5.698800252e-05 | -1.316060646e-06 | +1.754017598e-08 | +3.508033863e-08 |
| Block 7 | Network time | -4.780502350e-03 | -1.120931777e-04 | -1.754015599e-08 | +1.052409893e-07 |
| Block 7 | Scheduled pre-release wait | 0 | 0 | 0 | 0 |
| Block 8 | Source wait | +1.754017598e-08 | +2.382539653e-07 | +1.754017598e-08 | +1.648775823e-06 |
| Block 8 | Network time | -1.648775889e-06 | +1.010752220e-06 | -1.754015599e-08 | +7.752754705e-06 |
| Block 8 | Scheduled pre-release wait | 0 | 0 | 0 | 0 |

Scheduled pre-release wait is exactly unchanged. The tiny overall negative mean is almost entirely a block-7 network-time shift and does not transfer to block 8; this decomposition therefore reinforces, rather than relaxes, the preregistered Source no-support decision.

The three negative rows are only 4.837 ms of system-mean improvement each. They clear the 1 ms diagnostic epsilon but remain below the 10 ms usable-effect threshold, occur only in block 7, and cover only two diagnostic strata. They are not promotion positives. Block 8 has no beneficial row and therefore does not reproduce the direction.

All 176 p95 deltas, p99 deltas, and deadline-miss deltas are zero. The current-bag cost is at most one natural opportunity (1 ms), so all individual-cost and fairness gates pass. That safety result does not rescue the missing system effect.

## Preregistered gate result

| Gate | Result |
|---|---|
| Complete 256-group execution | PASS |
| H_system coverage = 128 block 7 + 48 block 8 | PASS |
| Action-changing rate ≥ 80% | PASS: 100% |
| At least 16 usable/strong fair system positives | FAIL: 0 |
| At least 4 block-8 usable/strong positives | FAIL: 0 |
| At least 3 promotion-positive strata | FAIL: 0 |

The pilot support decision is therefore **NO-GO**. The mechanism should remain opt-in research infrastructure, but there is no evidence-based reason to train a Source selector or run Source closed-loop scale claims.

## Smallest next step

Move one seam upstream to the already-existing local Route choice identified by the precursor plan. Test an alternative legal next edge or WAIT at that real junction while retaining S4/J2/E2, the same bounded horizons, and the same exact-pair discipline. If that Route action also lacks support, stop rather than layering more Source features, a larger learner, or centralized HCA-style planning onto the framework.

Compact machine-readable evidence is in [g4irsf23_source_pilot.csv](../tables/g4irsf23_source_pilot.csv) and [g4irsf23_source_pilot_summary.json](../tables/g4irsf23_source_pilot_summary.json). Raw census, target, pair, and label payloads remain under ignored `outputs/runtime/` and are not copied into Git.
