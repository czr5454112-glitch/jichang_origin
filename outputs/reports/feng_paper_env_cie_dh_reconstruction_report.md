# Feng paper-environment CIE-DH reconstruction report

## Outcome

The executable diagnostic is complete, but its scientific identity is
`SEMANTICALLY_PARTIAL_RECONSTRUCTION`, not a source-exact or higher-level
reproduction. The missing CIE-DH source and undisclosed mechanical details do
not block an executable paper-environment diagnostic, but they do limit the
claim that can be attached to it.

The historical workbook measurement and the executable result are kept as
separate evidence layers throughout this report:

- `FENG_PAPER_CIE_DH_HISTORICAL_MEASURED`: original Table 5.3 measurement;
  primary historical reference, not executable here.
- `FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION`: independent Java executable;
  semantic extrapolation in the Feng environment.

Interim campaign note (2026-09-05): the executable code and all results
available before a possible host shutdown are frozen in
`outputs/reports/cie_external_baseline_checkpoint_20260905.md`. The external
robustness matrix is explicitly incomplete at `164/180` normalized cells;
Nanning CIE-DH contributes `14/30` cells and no final cross-map claim is made.

## Direct answers to the required questions

1. **Was the original CIE-DH source recovered?** No. The exact-source track
   remains `SOURCE_NOT_RECOVERED`.

2. **Was an executable Feng-environment reconstruction completed?** Yes. The
   accepted branch completed all `28,506` raw bags and all `43,603` segments.
   Its formal level is `SEMANTICALLY_PARTIAL_RECONSTRUCTION` because the DH
   node handoff state machine and numerical penalties are not identified by
   source evidence.

3. **Which semantics are explicit and which are reconstructed?** Explicit
   paper semantics include map2/input parity, `2.5 m/s`, `0.2 s` updates,
   moving/stopped physical states, free-flow continuation plus separate
   moving/stopped penalties, greater stopped penalty, and local HOLD at a
   stopped outgoing entrance. The shared-D `sum(E-D)` population and timing
   formula are recovered from the workbook. The lattice, footprint, same-tick
   update details, tie-break, numerical coefficients, fixed transfer duration,
   and exact handoff state machine are frozen reconstruction assumptions.

4. **What penalties are used?** The main executable uses
   `alpha_move=0.4 s` and `beta_stop=0.8 s`. These are physically anchored
   assumptions, not recovered coefficients. The pre-frozen matrix remains
   `alpha/headway in {0.5,1,2}` by `beta/alpha in {1.5,2,3}`. Earlier outputs
   from the superseded handoff semantic were withdrawn; all nine cells have
   now been rerun with the final source identity.

5. **What is the Table 5.3 observation contract?** For each of the full
   `28,506` raw bags, sum every segment's `completion E - shared schedule D`.
   The shared D is identical in the HCA and DH workbook sheets. The planned
   EBS gap is excluded, but the fixed source induction and any source admission
   wait after D are included. First-edge admission is diagnostic only.

6. **How does the executable compare with the historical CIE-DH row?** The
   complete five-point comparison is below. The executable is faster than the
   historical row by `10.124%` at the mean and by `36.968%` at the maximum, so
   numerical proximity does not justify upgrading its identity.

7. **Did the original HCA change?** No legacy HCA source was modified. The
   previously frozen unchanged-HCA regression remains `43,603/43,603`
   segments, `28,506/28,506` raw bags and `188 / 236.710166 / 299 / 330 / 357 s`
   for min/mean/P95/P99/max. This admission-based HCA regression is not inserted
   into the shared-D Table 5.3 audit as though it had the same timestamp
   contract.

8. **How does G31 compare at map2 1×, 1.75×, and 2×?** On the final-source
   critical-load curve, G31 has lower complete-population mean/P95/P99/max in
   every eligible `1.00×`--`1.75×` cell. At `2×`, both methods complete
   `57,012/57,012`, but the partial DH executable has `56,379` on-time bags
   (`98.89%`) versus G31's `30,231` (`53.03%`), and lower total backlog AUC
   (`1.563e8` versus `2.935e8 bag-s`). The result is therefore `MIXED`, not a
   dominance claim. Formal `2×` THT is `N/A`.

9. **Is the conclusion stable across the coefficient envelope?** Yes for the
   limited fidelity finding: all nine complete-population cells remain faster
   than the historical measurement. Their mean/P95/P99/max ranges are
   `237.548–240.981 / 281.6–290.8 / 294.8–307.4 / 319.0–338.0 s`.
   Thus the coefficient uncertainty does not repair the missing historical
   mean or tail. This is a stable reconstruction limitation, not a basis for
   selecting the fastest cell.

10. **Do external paired seeds support G31 against reconstructed DH?** The
    answer remains not identified for the full cross-map matrix. At the
    2026-09-05 shutdown checkpoint, `164/180` normalized cells exist: map2 is
    complete and mixed at 1x (G31 mean is lower, but its P95/P99/max are
    higher), whereas the Nanning DH port has only `14/30` cells. Its seven 1x
    cells complete 44.530% on average and its four 1.75x cells complete
    44.308% on average. Its first three 2x cells complete 42.938% and deliver
    28.280% on time on average; formal 2x timing is N/A by protocol. Every
    Nanning DH cell remains full-population incomplete. These are interim
    diagnostics, not a final external ranking.

11. **What role remains for common-executor CIE-DH?** It remains a secondary
    route-policy isolation diagnostic. Neither executable variant can replace
    the historical measured Feng reference; both are secondary diagnostics.

12. **What caused the Nanning 2× maximum-tardiness degradation?** In the
    separate 20-run detail replay, all `20/20` maximum-tardiness bags are
    direct bags with zero source wait, and junction queueing accounts for
    `100%` of their recorded local wait. The worst one-percent population is
    distributed over `25/32` ODs in P0D0/P1D1, rather than one node-specific
    exception. This supports an expected capacity trade-off with
    junction-wait-dominated tail; priority starvation and route oscillation
    remain `NOT_IDENTIFIED_NO_TRACE_REPLAY`.

13. **What are the full 2×2 factorial main effects and interaction?** All five
    required scenarios and all four arms completed `10/10` frozen seeds. The
    potential and dynamic-state main effects and their interaction change with
    topology, load and metric. In Nanning `2×`, for example, the completion
    interaction is strongly antagonistic (`-8,885.2` bags), while the on-time
    interaction is `+339.2` and the backlog interaction is adverse. The
    supported conclusion is `MIXED`; no component receives a universal gain
    claim, and formal `2×` THT remains `N/A`.

14. **Were the failed Nanning ablation cells repaired?** Yes. The required
    `12/12` targeted `2×` cells now execute and pass their integrity gates,
    including the previously failed Nanning rows. They show topology-dependent
    necessity and negative or neutral cells, not a stable per-component win.

15. **What may be written now?** It is supportable that an independent,
    complete, semantically partial CIE-DH executable was built in the Feng
    map2 environment and that its Table 5.3 timing uses the recovered shared-D
    formula. It is not supportable to call it recovered source, original
    CIE-DH, a fully faithful reproduction, or evidence that G31 has beaten the
    unavailable historical implementation. The final critical-load comparison
    against the partial executable is mixed: G31 has lower eligible full-
    population timing through `1.75×`, whereas the partial executable has much
    stronger `2×` on-time and backlog outcomes. These extrapolated results do
    not change the historical Table 5.3 identity or level of CIE-DH.

## Accepted handoff semantics

The final branch uses one simple state machine:

1. Source: fixed `2.0 s` per-bag nonexclusive induction, then physical
   outgoing-edge admission.
2. Intermediate map node: `throughTime=1.0 s` is graph-node-local exclusive.
   During this stage, the bag retains its upstream edge footprint and is
   `STOPPED`, so downstream scarcity can propagate upstream.
3. After the one-second stage: release the upstream footprint and start a
   fixed `2.0 s` per-bag timer. These timers overlap and do not create another
   server.
4. Timer expiry: compete in the physical outgoing-edge FIFO and wait if the
   entrance cannot admit the footprint.
5. Goal: complete with no node or transfer service.

The fixed two-second duration is supported only by the 25 historical one-bag
OD lower envelopes. The Demo3D `TransferDuration=2` property is not treated as
independent validation of DH semantics.

## Historical measurement versus executable result

All values below use the recovered raw-bag `sum(E-D)` contract and the complete
population.

| evidence layer | min | mean | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|
| historical workbook measurement (s) | 213.3 | 265.592131481 | 336.9 | 384.595 | 517.2 |
| final executable reconstruction (s) | 206.4 | 238.702287238 | 285.2 | 300.8 | 326.0 |
| executable minus historical (s) | -6.9 | -26.889844243 | -51.7 | -83.795 | -191.2 |
| relative difference | -3.235% | -10.124% | -15.346% | -21.788% | -36.968% |

The paper prints only min/mean/max, rounded to `3.56 / 4.43 / 8.62 min`.
The workbook's exact corresponding values are `3.555 / 4.426535524685 /
8.62 min`; the executable values are `3.44 / 3.978371454 /
5.433333333 min`.

## Final executable identity

- Java source aggregate SHA-256: `99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8`.
- Compiled class aggregate SHA-256: `d611967f0433dfc08f67d92c89e9b13dcb5b8ac5ace3d3abec9c098dba360286`.
- Reconstruction manifest SHA-256: `abc496f173c517b2cd224356f3e9f4c5c2b21d1f525ebf570e4dac6ea510d2a4`.
- Frozen shared-D schedule SHA-256: `a3db0d3f495870437414af0b46a0a140f7cafe8111b40222ca59fcd78e7d4d86`.
- Mechanism tests: `10/10` passing; full accepted-configuration run status:
  `complete`.

The frozen manifest's legacy field named
`recovered_java_source_aggregate_sha256` (`b0c7545a...c9c25`) identifies the
untouched recovered Java/HCA evidence tree, not this CIE-DH implementation.
The authoritative reconstruction source and class hashes are the two full
values above; the manifest key is retained unchanged because its frozen hash is
already embedded in every final run identity.

The full executable recorded:

| integrity or mechanism counter | value |
|---|---:|
| completed raw bags | 28,506 / 28,506 |
| completed segments | 43,603 / 43,603 |
| stopped ticks | 1,872,897 |
| all holds | 2,282,929 |
| junction-through-busy holds | 49,194 |
| following-footprint holds | 361,338 |
| entry-stopped holds | 243,122 |
| entry-moving holds | 112,599 |
| outgoing-entry FIFO holds | 54,311 |
| mean segment source wait | 2.089076440 s |

The nonzero stopped and following-hold counts show that the final branch does
not erase physical congestion by moving bags off their upstream edges before
the map junction service completes. They do not, by themselves, prove that the
unavailable DH source used this state machine.

## Semantic sensitivity, not result fitting

The following candidates were specified to falsify alternative interpretations
of the same missing handoff detail. They did not add scorers, guards, route
conditions, or tuned coefficients.

| candidate | population | min / mean / P95 / P99 / max (s) | result |
|---|---:|---:|---|
| fully nonexclusive intermediate timing | full | 206.4 / 232.810952 / 271.0 / 271.2 / 273.6 | rejected: zero stopped ticks and only 5,296 holds; physical congestion propagation disappears |
| entire three seconds node-exclusive | full | 206.4 / 1057.2419 / 4363.15 / 6177.7 / 8767.2 | rejected: undocumented fixed-capacity collapse; 117,181,154 holds |
| upstream footprint retained for entire boundary service | first 1,000 | 209.6 / 350.8922 / 551.01 / 674.458 / 742.8 | rejected after bounded prefix; full run deliberately stopped |
| source-minimal executable extrapolation | full | 188.2 / 210.104876 / 246.4 / 249.6 / 260.0 | diagnostic only; not the historical measurement and not the final reconstruction |

The accepted hybrid branch is the smallest mechanism that preserves the old
map's one-second local junction resource and upstream stopped propagation
without turning the inferred two-second transfer timer into an undocumented
capacity server. This is a pre-frozen semantic sensitivity decision, not a
fit to Table 5.3.

## Fidelity gates

| gate | status | interpretation |
|---|---|---|
| exact DH source and coefficients | `SOURCE_NOT_RECOVERED` | no source-exact claim |
| paper algorithm semantics | `PASS` | explicit route and moving/stopped rules implemented |
| workbook population and shared-D formula | `PASS` | 28,506 raw bags, 43,603 segments, `sum(E-D)` |
| complete executable run | `PASS` | full raw and segment populations complete |
| node handoff state machine | `PARTIAL` | one evidence-bounded hybrid selected; source does not identify it |
| numerical coefficients | `PARTIAL` | physically anchored, undisclosed |
| historical numerical shape | `PARTIAL_MISMATCH` | mean and tail remain materially faster than workbook |
| final-branch coefficient envelope | `PASS_9_OF_9_COMPLETE` | every cell rerun under source `99bf...14d8`; no result-selected cell |
| paper use | `CONDITIONAL` | secondary executable diagnostic only; the historical measured row remains the primary CIE-DH performance reference |

OVERALL_DETERMINATION: READY_WITH_CONDITIONAL_DH_RECONSTRUCTION
