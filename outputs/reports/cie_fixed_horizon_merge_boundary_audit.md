# Fixed-horizon merge-boundary repair audit

Baseline: `4aeeda64cb7e9122c8d6e9e03705b03bafa62d8e`. Audited Nanning 2x cells: **6**; repaired mixed-boundary cells: **3**; review-required: **0**.

This is a fixed-horizon telemetry-identity repair only. It changes neither routing actions nor completion outcomes: the active grant bijection is now checked at the last executable boundary, before unfinished bags are converted to fixed-denominator reporting failures. It is not an algorithmic performance improvement.

| arm | before | after | completed old/new | failed old/new | time limit | active grants | pending | conservation | bijection | exact slot | current identity vs FULL_S4 | verdict |
|---|---|---|---:|---:|---|---:|---:|---|---|---|---|---|
| FULL_MINUS_I | NO_FALSE_EXECUTION_GATE | NO_FALSE_EXECUTION_GATE | 87206/87206 | 0/0 | False | 0 | 0 | True | True | True | True | UNCHANGED_PASS |
| FULL_MINUS_Q | CONSISTENT_WITH_CROSS_BOUNDARY_FINALIZATION_CHECK | NO_FALSE_EXECUTION_GATE | 86118/86118 | 1088/1088 | True | 43 | 2 | True | True | True | True | REPAIRED_FIXED_HORIZON_TELEMETRY_IDENTITY |
| FULL_MINUS_WS | CONSISTENT_WITH_CROSS_BOUNDARY_FINALIZATION_CHECK | NO_FALSE_EXECUTION_GATE | 86253/86253 | 953/953 | True | 42 | 4 | True | True | True | True | REPAIRED_FIXED_HORIZON_TELEMETRY_IDENTITY |
| FULL_S4 | NO_FALSE_EXECUTION_GATE | NO_FALSE_EXECUTION_GATE | 87206/87206 | 0/0 | False | 0 | 0 | True | True | True | True | UNCHANGED_PASS |
| H_ONLY_SERVICE_AWARE | NO_FALSE_EXECUTION_GATE | NO_FALSE_EXECUTION_GATE | 87206/87206 | 0/0 | False | 0 | 0 | True | True | True | True | UNCHANGED_PASS |
| H_PLUS_Q_PLUS_I | CONSISTENT_WITH_CROSS_BOUNDARY_FINALIZATION_CHECK | NO_FALSE_EXECUTION_GATE | 86253/86253 | 953/953 | True | 42 | 4 | True | True | True | True | REPAIRED_FIXED_HORIZON_TELEMETRY_IDENTITY |

The tracked evidence identifies `FULL_MINUS_Q`, `FULL_MINUS_WS`, and `H_PLUS_Q_PLUS_I` as the three failed cells. `FULL_MINUS_I` was already a passing cell in the baseline; any instruction listing it as failed is inconsistent with the executable artifacts.

Current executed-arm identity closure against `FULL_S4`: **True**. Binary SHA256: `b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5`; workload SHA256: `55538837011a1ed31eb272cc170fdc9fefb3b40ec14e2ae0574877a8c465a115`; base-request SHA256: `071c7270af404df8c75edb6da2b12dc7ca42547db09851098e8be3b12488c1aa`. A mixed current identity is review-required and cannot enter the paired table.

All 2x THT values remain protocol-level `NA`; no survivor/common-cohort timing is introduced.

## Exact rerun commands

```powershell
python scripts/eval/run_cie_targeted_ablation.py --map nanning --scale 2 --arm FULL_MINUS_I --canonical "C:\PROGRAMING\czr005\.cie_native_dh_worktree\build_cie_revision\workloads\g4irsf31_nanning\nanning_2x_canonical.jsonl" --binary "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\build\nanning_ablation_gate_f_pybind\python\Release\czr005_cpp.cp311-win_amd64.pyd" --activation-evidence "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\tables\cie_component_activation.csv" --revision-manifest "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\configs\eval\cie_revision_manifest.yaml" --output "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\runtime\cie_revision\targeted_ablation\FULL_MINUS_I\nanning_2x.json" --force
```
```powershell
python scripts/eval/run_cie_targeted_ablation.py --map nanning --scale 2 --arm FULL_MINUS_Q --canonical "C:\PROGRAMING\czr005\.cie_native_dh_worktree\build_cie_revision\workloads\g4irsf31_nanning\nanning_2x_canonical.jsonl" --binary "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\build\nanning_ablation_gate_f_pybind\python\Release\czr005_cpp.cp311-win_amd64.pyd" --activation-evidence "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\tables\cie_component_activation.csv" --revision-manifest "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\configs\eval\cie_revision_manifest.yaml" --output "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\runtime\cie_revision\targeted_ablation\FULL_MINUS_Q\nanning_2x.json" --force
```
```powershell
python scripts/eval/run_cie_targeted_ablation.py --map nanning --scale 2 --arm FULL_MINUS_WS --canonical "C:\PROGRAMING\czr005\.cie_native_dh_worktree\build_cie_revision\workloads\g4irsf31_nanning\nanning_2x_canonical.jsonl" --binary "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\build\nanning_ablation_gate_f_pybind\python\Release\czr005_cpp.cp311-win_amd64.pyd" --activation-evidence "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\tables\cie_component_activation.csv" --revision-manifest "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\configs\eval\cie_revision_manifest.yaml" --output "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\runtime\cie_revision\targeted_ablation\FULL_MINUS_WS\nanning_2x.json" --force
```
```powershell
python scripts/eval/run_cie_targeted_ablation.py --map nanning --scale 2 --arm FULL_S4 --canonical "C:\PROGRAMING\czr005\.cie_native_dh_worktree\build_cie_revision\workloads\g4irsf31_nanning\nanning_2x_canonical.jsonl" --binary "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\build\nanning_ablation_gate_f_pybind\python\Release\czr005_cpp.cp311-win_amd64.pyd" --activation-evidence "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\tables\cie_component_activation.csv" --revision-manifest "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\configs\eval\cie_revision_manifest.yaml" --output "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\runtime\cie_revision\targeted_ablation\FULL_S4\nanning_2x.json" --force
```
```powershell
python scripts/eval/run_cie_targeted_ablation.py --map nanning --scale 2 --arm H_ONLY_SERVICE_AWARE --canonical "C:\PROGRAMING\czr005\.cie_native_dh_worktree\build_cie_revision\workloads\g4irsf31_nanning\nanning_2x_canonical.jsonl" --binary "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\build\nanning_ablation_gate_f_pybind\python\Release\czr005_cpp.cp311-win_amd64.pyd" --activation-evidence "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\tables\cie_component_activation.csv" --revision-manifest "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\configs\eval\cie_revision_manifest.yaml" --output "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\runtime\cie_revision\targeted_ablation\H_ONLY_SERVICE_AWARE\nanning_2x.json" --force
```
```powershell
python scripts/eval/run_cie_targeted_ablation.py --map nanning --scale 2 --arm H_PLUS_Q_PLUS_I --canonical "C:\PROGRAMING\czr005\.cie_native_dh_worktree\build_cie_revision\workloads\g4irsf31_nanning\nanning_2x_canonical.jsonl" --binary "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\build\nanning_ablation_gate_f_pybind\python\Release\czr005_cpp.cp311-win_amd64.pyd" --activation-evidence "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\tables\cie_component_activation.csv" --revision-manifest "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\configs\eval\cie_revision_manifest.yaml" --output "C:\PROGRAMING\czr005\.feng_cie_dh_worktree\outputs\runtime\cie_revision\targeted_ablation\H_PLUS_Q_PLUS_I\nanning_2x.json" --force
```

The focused C++ regression constructs one exact grant in transit at a time cut and proves that the bag remains an honest `time_limit_reached` failure while the pre-finalization controller/capability/bag/calendar bijection passes.
