# G4IRSF24 DLP TD

Status: `MEASURED`.

- S4 remains the exact fallback for unsupported states.
- A candidate needs real native mutations and closed-loop business improvement before activation.
- TD Bellman zero-current is a baseline against the same frozen downstream target; the edge-score proxy cancels that downstream and is not presented as a clean S4/static comparison.
- DLP_TD_A: validation runtime/Bellman coverage=1.000000/1.000000, Bellman learned/zero-current=16.854137/32.726429s; held-out runtime/Bellman coverage=1.000000/1.000000, Bellman learned/zero-current=12.571566/25.948258s; DLP_TD_B: validation runtime/Bellman coverage=1.000000/1.000000, Bellman learned/zero-current=15.703022/29.674327s; held-out runtime/Bellman coverage=1.000000/1.000000, Bellman learned/zero-current=11.670230/22.903338s; DLP_TD_C: validation runtime/Bellman coverage=0.999941/0.999882, Bellman learned/zero-current=15.681632/29.637995s; held-out runtime/Bellman coverage=1.000000/1.000000, Bellman learned/zero-current=11.670230/22.903338s; DLP_TD_D: validation runtime/Bellman coverage=0.999941/0.999882, Bellman learned/zero-current=15.267676/24.415792s; held-out runtime/Bellman coverage=1.000000/1.000000, Bellman learned/zero-current=11.410096/17.835640s

## Offline validation and held-out test

| Candidate | Val runtime cov | Val Bellman cov | Val Bellman MAE | Val zero-current | Test runtime cov | Test Bellman cov | Test Bellman MAE | Test zero-current | Mutations | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DLP_TD_A | 1.0000 | 1.0000 | 16.854 | 32.726 | 1.0000 | 1.0000 | 12.572 | 25.948 | NOT_MEASURED | OFFLINE_NOT_SELECTED_NATIVE_NOT_RUN |
| DLP_TD_B | 1.0000 | 1.0000 | 15.703 | 29.674 | 1.0000 | 1.0000 | 11.670 | 22.903 | 0 | SCREEN_NO_MUTATION |
| DLP_TD_C | 0.9999 | 0.9999 | 15.682 | 29.638 | 1.0000 | 1.0000 | 11.670 | 22.903 | NOT_MEASURED | OFFLINE_NOT_SELECTED_NATIVE_NOT_RUN |
| DLP_TD_D | 0.9999 | 0.9999 | 15.268 | 24.416 | 1.0000 | 1.0000 | 11.410 | 17.836 | NOT_MEASURED | OFFLINE_NOT_SELECTED_NATIVE_NOT_RUN |

## Native 144/512 action accounting

| Candidate | Prefix | Route decisions | Eligible | Supported | Proposals | Mutations | Fallback | Unsupported | Low support | Margin | Detour | Shield/fault | Safe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DLP_TD_B | 144 | 989 | 1367 | 989 | 0 | 0 | 989 | 0 | 0 | 0 | 378 | 97 | PASS |
| DLP_TD_B | 512 | 3563 | 4890 | 3563 | 0 | 0 | 3563 | 0 | 0 | 0 | 1327 | 348 | PASS |
