# LT2 original-map R1 and finite-tray reuse evidence

This closes an original-map R1 execution gap and provides an original-map R2
advance-request witness. It does **not** close bidirectional coupling, method
novelty, normal-service protection for the changed route, full-flow business,
or complete-request 100 ms gates.

## Contract and prespecified denominator

`original_workload.research_r1_authorized` creates
`g31.research_r1_authorized.v1` on a deep copy. It adds explicit per-job
`allow_suffix_reroute=true` and a permission manifest. The old `build_input`
and original24 default inputs remain unchanged. All comparison branches have
the same permissions. Native delivery still checks identity, owner, executed
prefix, stage goal, deadline bound and live entry authorization. No topology,
direction, edge length, FIFO, capacity, destination or Storage requirement was
changed. The existing finite berth/port/owner model remains a research proxy;
this does not settle field semantics.

The census sees the entire original 1x projected source (28,506 jobs), static
positive-capacity edges, and mandatory stages only. It computes deterministic
shortest paths and every simple next-hop alternative at their divergence
points. Selection sorts arrival then business ID before loading native code.

| Census result | Jobs |
|---|---:|
| All required stages reachable and at least one alternative | 24,490 |
| Required stage unreachable | 4,001 |
| Reachable with no routing choice | 15 |
| Total retained in census | 28,506 |

The 4,001 and 15 are retained in the census; they are not removed from a formal
full-flow evaluation. Static choice is not a claim about live executability.

Two prespecified groups use the same first 16 eligible source jobs: their first
live choice and their first post-Storage/direct live choice. These are **32
contexts across 16 source jobs**, all from one legacy simulated source day,
not 32 independent operating samples. Each isolated context retains one
original job and one existing tray at its origin. This factor cannot establish
normal-business protection under the full source load.

## Actual native results

Binary: `build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd`.
SHA256: `af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0`.

Evidence under `outputs/experiments/g31_ics_lt2_20261014/`:

| Group | Contexts | Native branches | R1 physical witnesses |
|---|---:|---:|---:|
| `r1_storage_in_016` | 16 | 51 | 16 |
| `r1_post_storage_016` | 16 | 48 | 16 |

Each context forks one identical native checkpoint into a same-permission S4
control and all prespecified next-hop requests. Decisions use only the
delivered owner observation, static graph, public fault knowledge and route
codec. Offline state hashes and final receipts are used only for evaluation.
The codec records a proposed suffix, but the native request installs only its
next-hop preference. Subsequent hops remain under native S4 arbitration; these
results do not establish atomic installation of the entire encoded suffix.
The first downstream `EDGE_ENTER`, prefix, delivered ACK, complete business
denominator and lifecycle/capacity/headway replay are all checked. All 99
branches reached the common horizon, completed their job and passed the audit.
Source archives match the recorded hashes.

Concrete first example: `projected:1x:2` has committed edge 26→27. At
8888.531299, `owner:system_international` proposes next hop 27→2 instead of the
control's 27→28. Native validates at 8888.541299; ACK is delivered at
8888.741299. The physical next edge actually becomes 27→2. Mandatory Storage53
and final destination 116 are preserved. Storage entry is 79.54 seconds later than control,
but scheduled release at 19500 absorbs the difference, so completion remains
19772.592. This is a useful negative mechanism case.

Across the first-stage group, alternative paths change Storage arrival by
0.9–234.901 seconds but all completion differences are zero. Across the
post-Storage group, alternatives change completion by 0.9, 73.801 or 231.352
seconds. These deliberate alternatives are mostly worse than S4; physical
controllability is established, algorithmic improvement is not.

## R1 release change, R2 advance request and two reuses

`r1_reuse_002` is the authoritative six-branch continuation. `r1_reuse_001`
is retained as **invalidated by source-change guard**: controller files were
being finalized during that run; do not promote it as the final evidence.

The unchanged static round-trip rule selects original jobs 2, 6, 23 at loader 26,
using one original tray. At the first post-Storage choice, control/50→25/50→34
are crossed with reactive/predictive event R2 continuation. Further R1 updates
are disabled by contract. All six branches complete all 3 jobs, execute 2 real
cross-zone returns, and pass lifecycle/capacity/headway replay. Source hashes
are unchanged during the authoritative run.

For predictive control, successful transfer requests are submitted 15.95 and
344.843 seconds before actual empty release. Export waits for real release;
the forecast never creates a tray or bypasses authorization. Relative to the
reactive continuation, predictive control removes 2 seconds of waiting at each
return and improves the second job completion by 2 seconds; the third job's
Storage gate absorbs the accumulated difference.

Changing the first post-Storage hop from 50→34 to 50→25 delays unload, hold
completion, real export, empty reception and the next job's load/completion by
0.9 seconds. The same tray is reused twice. The third Storage gate absorbs the
delay. This proves one-way R1→release→R2→future supply propagation. It does not
show R1 responding again to a changed competing resource occupancy.

`factorial_diagnostics_002.json` evaluates all four complete executable cells
per route alternative and binds their three business identities to the saved
`selection.json`. This is an **R1 × R2-policy factorial contrast**, not a
same-continuation joint-action κ: the R2 factor changes the continuing policy
between reactive and predictive cells. Both completion-sum contrasts are exactly
0 in the saved double results. The legacy `kappa_completion_sum_seconds` numeric
field remains as a compatibility alias, with an explicit `comparison_scope` and
`same_continuation_joint_action_kappa=false`. It does not test joint-action
nonseparability under a common continuation. The original
`factorial_diagnostics.json` remains unchanged as a historical artifact.

The best enumerated route equals S4 control within each R2 continuation;
observed finite route-domain headroom is 0. The 50→25 action violates the
zero-regression rule for two jobs (+0.9 seconds each). It is a negative action,
not an acceptable improved policy. Higher-order contention remains unknown.

## Verification and continuation

`r1_tests_002.xml`: 25 passed, including original workload regressions, deep
copy/permission isolation, census exclusion preservation, real first-stage and
post-Storage traversal changes, delayed stale-prefix rejection and unpermitted
route rejection with legal original continuation.
`r1_interaction_tests_003.xml`: 17 passed. Missing control/action cells,
incomplete horizons, rejected actions, changed sources, duplicate job IDs,
missing/nonfinite times and conflicting offered-ID contracts remain unknown.
The offered-ID guard also detects a job silently omitted from every cell.
Without an offered-ID manifest, the assessor labels its denominator as observed
branch IDs only. A shared clock or a completed subset cannot establish a full
offered-business denominator.

Verified run command, with a fresh output directory:

```powershell
$env:PYTHONPATH='src'
python -m scripts.experiments.g31_ics_circulation.research_r1_reuse --binary build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd --expected-binary-sha256 af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0 --output outputs/experiments/g31_ics_lt2_20261014/r1_reuse_next
```

This reconstructs a fresh deterministic start; it is not cross-process native
checkpoint restoration. The next research task is a prespecified two-owner,
two-or-more-tray shared receiving/edge/headway context with competing actions,
then matched four-cell and higher-order native continuation. Keep the present
absorbed and separable cases as negative controls; do not repeatedly train on
this saturated one-tray local domain. R1/R2 and the full-request 100 ms target
remain in force.
