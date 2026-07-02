# G4H C++ Runtime Parity Report

Date: 2026-07-02
Branch: `codex/czr005-rewrite`
HEAD: `dc3891b`
Contains G4F/G4G: `True` / `True`
Pushed to upstream at runtime: `False`

## Scope

Python event loop calls the C++ G4H action core for model scoring, risk abstain, and PIBT-lite fallback action selection. Full standalone C++ batch replay is deferred to G4I.

## Result Table

| Window | Actions | Pred mismatch | Fallback mismatch | Action mismatch | Pass |
| --- | --- | --- | --- | --- | --- |
| g4d_first1024_no_fault | 8139 | 0 | 0 | 0 | True |
| g4d_first144_no_fault | 1138 | 0 | 0 | 0 | True |
| g4d_first256_no_fault | 2012 | 0 | 0 | 0 | True |
| g4d_first512_no_fault | 3967 | 0 | 0 | 0 | True |
| g4d_offset2048_1024_high_density | 7947 | 0 | 0 | 0 | True |
| g4d_offset512_512_high_density | 4172 | 0 | 0 | 0 | True |
| g4d_offset64_repair512 | 3968 | 0 | 0 | 0 | True |
| g4d_offset64_static512 | 3892 | 0 | 0 | 0 | True |

## Negative Findings

This is action-level C++ parity, not yet a standalone C++ full batch replay.
