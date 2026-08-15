# G4IRSF24 DLP EWMA

Status: `MEASURED`.

- S4 remains the exact fallback for unsupported states.
- A candidate needs real native mutations and closed-loop business improvement before activation.
- EWMA learned edge residual is compared directly with the zero-residual S4 proxy on chronological validation and held-out test.
- DLP_EWMA_A: validation edge learned/static=13.472755/8.920642s, held-out edge learned/static=8.756412/2.596602s; DLP_EWMA_B: validation edge learned/static=13.472755/8.920642s, held-out edge learned/static=8.756412/2.596602s; DLP_EWMA_C: validation edge learned/static=13.472755/8.920642s, held-out edge learned/static=8.756412/2.596602s; DLP_EWMA_D: validation edge learned/static=12.209582/8.920642s, held-out edge learned/static=7.476283/2.596602s

## Offline validation and held-out test

| Candidate | Val runtime coverage | Val edge MAE | Val zero residual | Test edge MAE | Test zero residual | Mutations | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DLP_EWMA_A | 1.0000 | 13.473 | 8.921 | 8.756 | 2.597 | NOT_MEASURED | OFFLINE_NOT_SELECTED_NATIVE_NOT_RUN |
| DLP_EWMA_B | 1.0000 | 13.473 | 8.921 | 8.756 | 2.597 | NOT_MEASURED | OFFLINE_NOT_SELECTED_NATIVE_NOT_RUN |
| DLP_EWMA_C | 1.0000 | 13.473 | 8.921 | 8.756 | 2.597 | NOT_MEASURED | OFFLINE_NOT_SELECTED_NATIVE_NOT_RUN |
| DLP_EWMA_D | 1.0000 | 12.210 | 8.921 | 7.476 | 2.597 | 0 | SCREEN_NO_MUTATION |

## Native 144/512 action accounting

| Candidate | Prefix | Route decisions | Eligible | Supported | Proposals | Mutations | Fallback | Unsupported | Low support | Margin | Detour | Shield/fault | Safe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DLP_EWMA_D | 144 | 989 | 1367 | 989 | 0 | 0 | 989 | 0 | 0 | 0 | 378 | 97 | PASS |
| DLP_EWMA_D | 512 | 3563 | 4890 | 3563 | 0 | 0 | 3563 | 0 | 0 | 0 | 1327 | 348 | PASS |
