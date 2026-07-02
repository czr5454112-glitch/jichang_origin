# G4G Stress Window Report

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `7fdf7c0`
Contains G4F `7fdf7c0`: `True`
Dirty at runtime: `True`
Pushed to upstream at runtime: `False`

## Scope

Run no-full-A* goal-reaching simulation on additional raw inputdata windows: six 512-task offsets, four 1024-task offsets, two 2048-task smoke windows, and one 4096-task smoke window.

## What Is Claimed

The official candidate is measured on larger raw task windows without using full CIE/A* runtime fallback.

## What Is Not Claimed

Raw stress windows do not have freshly generated CIE teacher planned scope; they are runtime stress evidence, not teacher parity evidence.

## Repro Command

`python scripts/eval/run_g4g_no_astar_fallback_validation.py`

## Result Table

| Window | Size | Planned | Conflicts | Full A* | Stable |
| --- | --- | --- | --- | --- | --- |
| g4g_1024_offset0_no_fault | 1024 | 1024/1024 | 0 | 0 | True |
| g4g_1024_offset1024_no_fault | 1024 | 1024/1024 | 0 | 0 | True |
| g4g_1024_offset2048_no_fault | 1024 | 1024/1024 | 0 | 0 | True |
| g4g_1024_offset4096_no_fault | 1024 | 1024/1024 | 0 | 0 | True |
| g4g_2048_offset0_no_fault | 2048 | 2048/2048 | 0 | 0 | True |
| g4g_2048_offset2048_no_fault | 2048 | 2048/2048 | 0 | 0 | True |
| g4g_4096_offset0_no_fault | 4096 | 4096/4096 | 0 | 0 | True |
| g4g_512_offset0_no_fault | 512 | 512/512 | 0 | 0 | True |
| g4g_512_offset1024_no_fault | 512 | 512/512 | 0 | 0 | True |
| g4g_512_offset1536_no_fault | 512 | 512/512 | 0 | 0 | True |
| g4g_512_offset2048_no_fault | 512 | 512/512 | 0 | 0 | True |
| g4g_512_offset4096_no_fault | 512 | 512/512 | 0 | 0 | True |
| g4g_512_offset512_no_fault | 512 | 512/512 | 0 | 0 | True |

## Negative Findings

No raw stress window has new CIE teacher labels in G4G; G4H should focus on runtime parity rather than expanding teacher claims.

## Next Blocking Question

Does the same ladder remain stable and fast in C++ over the 4096-task smoke window?
