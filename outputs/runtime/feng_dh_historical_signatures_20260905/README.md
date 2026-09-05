# Historical Feng DH timing diagnostics

Read-only map2 audit of the exact frozen historical workbook against shared-D primary DH segments. No simulation code or original workbook was changed. Findings and interpretation are in `outputs/reports/feng_dh_historical_timing_signatures_20260905.md`.

Run from the repository root with a Python environment containing numpy and pandas:

```powershell
python scripts/eval/audit_feng_dh_historical_signatures.py --workbook 'C:/path/to/仿真结果数据整理（与分散启发式方法对比）.xlsx'
```

The script checks the workbook's exact SHA-256 before reading it. Full source rerun also needs the original `outputs/runtime/feng_cie_dh_reconstruction/primary/segments.csv` and `runner_status.json`, the tracked map and raw input, and `regression_final/repaired_map2_single_bag.jsonl.gz`. The source workbook is external; it is not silently replaced by a newly generated workbook.

For review without the external workbook or large primary file, `paired_segments.csv.gz` contains all 43,603 aligned observations, raw bag and segment IDs, original DH Excel rows, shared release D, historical DH/HCA durations, current duration, current source wait, and isolated-route timing. Historical E is recoverable as D plus its duration. This is a numerical audit extract at 9 decimal places, not a byte copy of the workbook XML. Its decompressed SHA-256 is `2103fdd1280a7ef257de8c812dea28b93bf9f9fe188987937786f20f5e47fedd`. Group by raw bag ID and sum each duration to recover the headline 28,506-bag metrics in `summary.json`.

`od_minimum_timing_signatures.csv` gives all 25 ODs and diagnostic route bounds. `smallest_historical_per_od.csv` links their minima to original rows. `by_leg_kind.csv`, `by_bag_segment_count.csv`, release-density tables, and `historical_completion_residues.csv` support the composition, workload, and timestamp claims. `manifest.json` lists sizes and SHA-256 checksums for these artifacts and identifies each source dependency.

The 3.1-second expression is only a diagnostic signature; it is contradicted as a universal fixed service parameter by 53→50 and 2→50 minima. The isolated distance-shortest route is not a global physical-time lower bound.
