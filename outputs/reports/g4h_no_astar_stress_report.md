# G4H No-A* Stress Report

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `dc3891b`
Contains G4F/G4G: `True` / `True`
Pushed to upstream at runtime: `False`

## Scope

Stress the official no-A* candidate on 8x512, 6x1024, 3x2048, 2x4096, and 1x8192 raw inputdata windows.

## Result Table

| Window | Size | Planned | Conflicts | Full A* | Rule Calls | Stable |
| --- | --- | --- | --- | --- | --- | --- |
| g4h_1024_offset0_no_fault | 1024 | 1024/1024 | 0 | 0 | 1478 | True |
| g4h_1024_offset1024_no_fault | 1024 | 1024/1024 | 0 | 0 | 1661 | True |
| g4h_1024_offset2048_no_fault | 1024 | 1024/1024 | 0 | 0 | 1912 | True |
| g4h_1024_offset3072_no_fault | 1024 | 1024/1024 | 0 | 0 | 1956 | True |
| g4h_1024_offset4096_no_fault | 1024 | 1024/1024 | 0 | 0 | 2097 | True |
| g4h_1024_offset8192_no_fault | 1024 | 1024/1024 | 0 | 0 | 2152 | True |
| g4h_2048_offset0_no_fault | 2048 | 2048/2048 | 0 | 0 | 3139 | True |
| g4h_2048_offset2048_no_fault | 2048 | 2048/2048 | 0 | 0 | 3868 | True |
| g4h_2048_offset4096_no_fault | 2048 | 2048/2048 | 0 | 0 | 3999 | True |
| g4h_4096_offset0_no_fault | 4096 | 4096/4096 | 0 | 0 | 7007 | True |
| g4h_4096_offset4096_no_fault | 4096 | 4096/4096 | 0 | 0 | 8249 | True |
| g4h_512_offset0_no_fault | 512 | 512/512 | 0 | 0 | 714 | True |
| g4h_512_offset1024_no_fault | 512 | 512/512 | 0 | 0 | 760 | True |
| g4h_512_offset1536_no_fault | 512 | 512/512 | 0 | 0 | 901 | True |
| g4h_512_offset2048_no_fault | 512 | 512/512 | 0 | 0 | 916 | True |
| g4h_512_offset3072_no_fault | 512 | 512/512 | 0 | 0 | 983 | True |
| g4h_512_offset4096_no_fault | 512 | 512/512 | 0 | 0 | 1006 | True |
| g4h_512_offset512_no_fault | 512 | 512/512 | 0 | 0 | 764 | True |
| g4h_512_offset8192_no_fault | 512 | 512/512 | 0 | 0 | 1067 | True |
| g4h_8192_offset0_no_fault | 8192 | 8192/8192 | 0 | 0 | 15256 | True |

## Negative Findings

Raw stress windows are runtime stress evidence and do not add new CIE teacher labels.
