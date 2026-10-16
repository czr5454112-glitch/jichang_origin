# LT2 synthetic finite-tray reuse chain — 2026-10-14

The complete predeclared 24-cell synthetic domain has one protected gain: at the intermediate storage gate, the best enumerated initial route/window decision improves total completion time by **1.41 seconds** over the best of four fixed-initial-route departure windows, with exact zero regression for each of the four offered jobs. The other two gate regimes have **zero protected gain**. These are finite-domain native reference results, not continuous-window optimality, a full B2 implementation, B3/MPC, B4/LNS, a new online joint solver, or an airport result.

The executable study is [research_synthetic_reuse_chain.py](../../scripts/experiments/g31_ics_circulation/research_synthetic_reuse_chain.py). The authoritative assessment is [independent_assessment.json](../../outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_003/independent_assessment.json), which reassesses the saved native outputs using strict per-job delta `<= 0`. The [native execution receipt](../../outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_003/receipt.json) and [predeclared protocol](../../outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_003/preregistered_protocol.json) remain unchanged.

## Fixed domain and information

There are two trays, L and E, and four jobs observed before the common native checkpoint at 0.11 seconds. L serves `loaded`, unloads at node6, physically returns empty across the owner boundary to node7, serves `reuse1`, returns to node7 again, and serves `reuse2`. E transfers from node5 to serve `receiver` at node1 and finishes at node4. Node4 has capacity 2 and its export permission is disabled in **every** cell, so E cannot silently substitute for L. Stock, topology, offered jobs, capacities, permissions, and continuation are identical within each gate regime.

This new graph, mandatory on-carrier storage at node4, public operation duration of 3 seconds, and fixed module permissions are explicitly synthetic factors. No original map/workload or physical rule was changed. Node3 has resource owner B and logistics zone A; this declared distinction lets A publish an E-to-node3 service forecast to the owner responsible for that shared resource.

The three storage release gates are `3 × {0,2,4}` = 0,6,12 seconds. The two initial choices are retain native route0→1 (no command) and request route0→2. Four E departure windows are derived before outcomes from public durations: 0.11, `0.11 + service0 + travel0→1 + service1` = 2.21, `0.11 + 3` = 3.11, and `0.11 + 6` = 6.11 seconds. All 3×2×4 cells were retained.

Every cell starts from its gate's identical native checkpoint and public owner views. The common continuation uses public 0.05-second ticks, immutable 0.5-second transport retries, owner-local physical observations, delivered demand, and delivered conditional service forecasts. A source at node6 requests each L return only when L is actually empty and available and B's waiting node7 demand has arrived. B's later route choice at node7 uses a delivered E-to-node3 forecast and a declared public 3-second lookahead: bypass through node8 when the forecast intersects that window, otherwise retain node3. Forecasts are soft estimates; native owner validation and resource constraints still apply. Policy code does not inspect native results, the future event queue, or an offline fork outcome.

## Native results and protection

Every final cell reached the common 40-second horizon, completed exactly the four offered jobs, preserved the two trays, passed the independent physical receipt audit, and witnessed **two actual L empty returns followed by two L reloads**. All selected route commands received `updated` ACKs and matched actual next-edge receipts; all three transfer intents per cell received terminal `received` ACKs. Retaining an existing route is a no-op and is verified by its actual edge.

The incumbent is fixed before outcomes as initial route0→1/window1 within each regime. Protection checks every offered job against that incumbent. The fixed-route reference enumerates all four departure windows with the same later continuation. The joint reference enumerates all eight initial route/window choices with that continuation. Both minima are reported only after all eight cells are assessed.

| Storage gate | Predeclared κ, seconds | Best protected fixed initial route | Best protected enumerated initial choice | Protected gain over fixed family | Separate feedback witness |
|---|---:|---|---|---:|---|
| 0 | -6.941 | route0→1/window1 | route0→1/window1 | 0 | Yes |
| 6 | -2.141 | route0→1/window1 | route0→2/window0 | 1.41 | Yes |
| 12 | +0.680 | route0→1/window0 | route0→1/window0 | 0 | No |

κ uses the predeclared two initial suffixes and window0/window1, with objective equal to the sum of all four completion times. It measures nonseparability in this controlled continuation, not a novelty claim.

At gate6, the protected comparison is:

| Offered job | Best fixed-route family, seconds | Best enumerated choice, seconds | Difference |
|---|---:|---:|---:|
| loaded | 6.80 | 6.80 | 0 |
| receiver | 8.01 | 6.60 | -1.41 |
| reuse1 | 12.22 | 12.22 | 0 |
| reuse2 | 17.67 | 17.67 | 0 |

The gate absorbs the loaded-job route difference in this winning comparison. The two subsequent reuses remain physically necessary and their completion times remain equal. With gate0, the detour causes protected-job regressions and offers no admissible gain. With gate12, the fixed route and early supply already win; the initial route's release/return effect is absorbed. Both negative regimes remain in the reference.

## Feedback and gain are separate witnesses

In gates0/6, changing initial R1 changes L's initial unload time and first real return time in paired cells. At gate6/window0, the detour advances unload by 0.921 seconds and first actual return by 0.95 seconds. Separately, changing R2's departure window changes the actually delivered E forecast and B's subsequent `reuse1` route choice from node3 to node8; native ACK and edge receipts confirm the changed command.

**The node8 feedback choices occur in window3 cells that fail all-offered protection. The protected gate6 winner retains node3.** Thus the experiment establishes a legal bidirectional mechanism and a protected finite-reference gain as separate findings. It does not establish that the late feedback is necessary for the gain, or that an online solver can discover the winning initial choice. Gate12 has neither the paired release/return effect nor a changed later route choice.

## Reproducibility, corrections, and validation

Native artifact: `build_lt_session_016/python/czr005_circulation.cp311-win_amd64.pyd`, SHA256 `af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0`. Final execution used one native worker, a 180-second hard timeout, and 5.12 seconds worker wall time. This aggregate runtime and 50 ms policy cadence do not certify the complete 100 ms request requirement.

- [Attempt001](../../outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_001/receipt.json) stopped before loading native because a final-state hash was mistakenly supplied as the expected binary hash; zero branches executed.
- [Attempt002](../../outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_002/receipt.json) preserves 24 initial cells. The harness incorrectly reaffirmed the existing route with a command. Native `receiving_full` rejection made four cells unresolved under the selected-command criterion, despite complete physical jobs. The correction made the intended “keep existing route” choices actual no-ops; no gate, window, stock, job, or topology changed.
- [Attempt003](../../outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_003/process.json) reran all 24 cells. Total native branch count is 48. No cells were selected or dropped using outcomes, and no further native branches were run.
- After execution, independent review strengthened only `assess_cell` and `assess_regime`: exact finite offered-job rows and horizon, physical audit success, exact eight-cell keys, explicit unknown handling, strict zero regression, and JSON-native report values. The [offline verifier](../../outputs/experiments/g31_ics_lt2_20261014/verify_synthetic_reuse_chain_saved.py) proves every other non-import AST node is identical to the archived execution source, rechecks all raw native evidence and checkpoint identities, and confirms all 24 cell/regime conclusions unchanged. Its receipt records both source hashes and evidence hashes.
- [Tests](../../tests/test_g31_circulation_synthetic_reuse_chain.py) passed **17/17**, including saved-native reassessment, immutable retries, delivered-before-decision causality, finite/exact-job and audit failure guards, incomplete-domain handling, tombstone identity, and rejection of a positive 1e-12 regression. [Final XML](../../outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_tests_002.xml). [Initial XML](../../outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_tests_001.xml) preserves a reporting-only tuple/list comparison failure fixed before final verification.

The native execution command is recorded in the receipt. Read-only verification is reproducible with `PYTHONPATH=src;.` and:

```text
python outputs/experiments/g31_ics_lt2_20261014/verify_synthetic_reuse_chain_saved.py
```

The saved-evidence test additionally requires `G31_REUSE_CHAIN_EVIDENCE=outputs/experiments/g31_ics_lt2_20261014/synthetic_reuse_chain_003` and runs:

```text
python -m pytest tests/test_g31_circulation_synthetic_reuse_chain.py -q
```

The next scientific requirement remains an online same-information proposal mechanism and strong, accurately labelled optimization baselines. These 24 cells do not complete that requirement or establish airport-wide feasibility.
