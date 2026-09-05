# Optimized executable: complete P2 regression and equivalence evidence

The optimized executable passes the complete workload regression and preserves
the correctness-frozen executable's audited behavior byte for byte.

| Version | Production source aggregate SHA-256 | Production class aggregate SHA-256 |
|---|---|---|
| Correctness freeze | `3b47ffcefa558365e55e27508fc8904608026fd3235102eee6c305539999a208` | `21fc22d8cd27628e2933eb73256cafa6f2bd695628fd46988ea445aafd7a5d47` |
| Equivalent optimization | `809d069832da3fec5a2aa6302a99a9ede24fcd5a1fb28c4a53c3cc3c139ff86f` | `ad828f533bc34abb3527d92f0f476e69412fc14c0024cbf2694bf0f82b382fd0` |

Both identities above were read from their completed native population runner
statuses. Audit class aggregates additionally include the independent OD
harness. Production source bytes use CRLF for frozen Windows checkout identity.

| Regression | Result |
|---|---|
| Map2 formal ODs | 25/25 independent single bags complete |
| Nanning formal ODs | 496/496 independent single bags complete |
| Extra topology witness 130→57→58 | Complete at tick 251 |
| All 522 OD service-event records | Byte-identical to correctness freeze |
| Original map2 full population | 28,506/28,506 bags and 43,603/43,603 segments complete |
| All map2 bag/segment/event outputs | Byte-identical to both original `99bf...` and corrected `3b47...` |
| Original-version ODs without zero intermediates | All 174 complete records remain byte-identical |

`correctness_to_optimized_equivalence.json` records the exact before/after
SHA-256 values for every single-bag JSONL, full-population bags and segments,
event summary and trace output. All comparisons pass. The native population
summary's only difference is wall_seconds: 32.1528051 for the correctness
freeze, 30.2817981 for this optimization run. These are recorded execution
times from regression runs; the equivalence conclusion does not depend on
their relative speed.

The complete 60-cell frozen workload coverage and original `99bf...` failure
evidence are inherited byte for byte from `../regression_final/`. All raw
file SHA-256 values, expanded population counts and deduplicated OD provenance
remain available in `formal_od_coverage.json`, the two formal-OD TSV files,
and the `old_*` evidence. No old failing simulation was rerun or merged into
the corrected population results.

The Nanning business witness, raw bag 7007/segment 0 from seed 104729 1×,
still completes at tick 755 after passing zero-time node 56. Its original
failure at tick 690 and the repaired full service-event record are retained
in the two `*_formal_business_witness.json` files. OD tests reset release to
tick 0 and are correctness checks, not population performance measurements.

`single_bag_od_comparison.csv` provides a compact row for every OD. Six
deterministic `.jsonl.gz` archives retain all underlying service-event records,
with compressed and uncompressed hashes in
`single_bag_equivalence_and_archives.json`. Native complete population CSVs
are retained locally and bound by SHA-256 in both comparison JSON files;
compact native summaries and runner identity are committed alongside them.

To repeat optimized checks from the repository root with the same input
workloads and the reference evidence already present, select a fresh evidence
directory, copy its `old_*`, formal-OD TSV and coverage files from
`regression_final`, then run:

```powershell
$evidence = 'outputs/runtime/feng_cie_dh_zero_through_repair_20260905/regression_optimized'
$reference = 'outputs/runtime/feng_cie_dh_zero_through_repair_20260905/regression_final'
python scripts/eval/audit_feng_zero_through_regression.py audit --version repaired --output-dir $evidence
python scripts/eval/audit_feng_zero_through_regression.py regression --output-dir $evidence
python scripts/eval/audit_feng_zero_through_regression.py summarize --output-dir $evidence
python scripts/eval/audit_feng_zero_through_regression.py compare-reference --output-dir $evidence --reference-dir $reference
```

Each evidence directory now receives its own independent build directory.
The original `build/feng_cie_dh_zero_through_fix_v1` executable remains intact.
Use fresh output directories for reruns because completed native runs are
protected against overwrite.
