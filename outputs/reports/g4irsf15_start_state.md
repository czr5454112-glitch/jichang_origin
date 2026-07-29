# G4IRSF15 Stage 15A start state

## Repository and protected inputs

- Repository: `czr5454112-glitch/jichang_origin`
- Stage base: `966a063573f0419df1324708db75211c521d59db`
- Generation branch: `codex/g4irsf15-execution`
- Generation HEAD: `966a063573f0419df1324708db75211c521d59db`
- Upstream: `origin/codex/czr005-rewrite` at `966a063573f0419df1324708db75211c521d59db`
- The base commit is an ancestor of both HEAD and upstream.
- Protected map: `data/processed/maps/map2.json` raw `9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4`, semantic `67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63`.
- Protected tasks: `data/processed/tasks/inputdata.jsonl` raw `968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f`, 43,603 segments and 28,506 raw bags.
- No G4IRSF12--14 artifact is rewritten. Stage 15 copies only selected values and binds predecessor content.

## Frozen controls

| Role | Exact binary SHA-256 |
|---|---|
| Final F2 control | `814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7` |
| Original-1x E4 screening | `11b957890666a4ac4dd056fca4828cecb6b3f3ff29fdc590d05c4cff875ebc71` |
| Stage-D E4 mechanism | `0d82141e8e650d682f812fe18582661ba6feb6dd08c88731c343d3caf07d6a38` |
| Event-microphase instrumented runtime | `e10da3f5fcf49d3522eb51e70523b2b8d2d2a747cee07d3991d9f74de1efb233` |

F2 remains `R3/S1/P2/C0/Q0`, reservation depth 1. Its original-entry mean is `41.514218717973414` minutes, versus frozen v2-safe `41.49530698780892` minutes and corrected historical HCA `43.13593828041816` minutes. The gap to v2-safe remains `+1.1347038098698192` seconds per bag.

## G4IRSF14 handoff

- Prior decision: `PARTIAL_WITH_EXPLICIT_BLOCKER`.
- Formal complete causal labels: `0`; H_system pairs: `0`.
- E4 original-1x requests/arbitrations: `335,770` / `335,770`.
- Active-grant rejections: `178,263`.
- Live multi-request boundaries: `1`; peak pending: `2`.
- Lifecycle rows dropped by the bounded passive trace: `1,011,439`.

This freeze does not authorize training, closed-loop evaluation, scaling, or a performance claim. Stage 15C must first rematerialize exact target descriptors and execute action-changing same-state pairs.

## GitHub Actions boundary

No G4IRSF15 workflow run exists at generation time. A run URL, run ID, job ID, and artifact hash must be appended by the publishing task after push; this bundle does not claim an unobserved CI result.
