# G4IR2 Scale And Generalization Report

Date: 2026-07-03
Branch: `codex/czr005-rewrite`
HEAD: `5d4be59`
Upstream: `origin/codex/czr005-rewrite`
Upstream HEAD: `5d4be59`

## Scale Ladder

| Scenario | Planned | Conflicts | Full A* | Seconds |
| --- | --- | --- | --- | --- |
| g4ir2_scale_512_offset0_no_fault | 512/512 | 0 | 0 | 0.03426929982379079 |
| g4ir2_scale_1024_offset0_no_fault | 1024/1024 | 0 | 0 | 0.0832967001479119 |
| g4ir2_scale_2048_offset0_no_fault | 2048/2048 | 0 | 0 | 0.24073110008612275 |
| g4ir2_scale_4096_offset0_no_fault | 4096/4096 | 0 | 0 | 0.7670836998149753 |
| g4ir2_scale_8192_offset0_no_fault | 8192/8192 | 0 | 0 | 2.8353766000363976 |
| g4ir2_scale_12000_offset0_no_fault | 12000/12000 | 0 | 0 | 6.347064699977636 |
| g4ir2_scale_16000_offset0_no_fault | 16000/16000 | 0 | 0 | 11.558461399981752 |
| g4ir2_scale_24000_offset0_no_fault | 24000/24000 | 0 | 0 | 26.769942700164393 |
| g4ir2_scale_32000_offset0_no_fault | 32000/32000 | 0 | 0 | 47.96546559990384 |

## Density And Fault Stress

Synthetic density rows compress task entry times only for stress testing. They are not new verified Java teacher data.
