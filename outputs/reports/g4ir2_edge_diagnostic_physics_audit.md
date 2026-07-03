# G4IR2 Edge Diagnostic Physics Audit

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `5d4be59`
Upstream: `origin/codex/czr005-rewrite`
Upstream HEAD: `5d4be59`

## Top Diagnostic Edges

| Edge | Moves | Overlap Sum | Primary? |
| --- | --- | --- | --- |
| 44->50 | 3192 | 209544 | False |
| 37->49 | 2693 | 116401 | False |
| 52->29 | 2238 | 99367 | False |
| 52->40 | 2001 | 86679 | False |
| 45->48 | 1876 | 84173 | False |
| 27->28 | 5092 | 27904 | False |
| 32->37 | 2174 | 15923 | False |
| 46->36 | 2462 | 14245 | False |
| 22->24 | 3113 | 11468 | False |
| 18->22 | 3307 | 10538 | False |

Edge overlap remains a diagnostic counter because conveyor motion in the verified CIE/Java line is not modeled as a strict edge_capacity=1 resource.
