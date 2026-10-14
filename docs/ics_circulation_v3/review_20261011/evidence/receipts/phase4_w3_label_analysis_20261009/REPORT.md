# W3 共同未来标签机会诊断

本报告仅分析已完成的开发标签，不训练模型，不构成独立确认。

| 状态 | 时刻 | 保留干预ID | 即时物理前缀 | 样本价值类 | 候选覆盖损失 | timed选择损失 |
|---|---:|---:|---:|---:|---:|---:|
| stream_L2_D1_slack3:timed:t0:initial | 0 | 12 | 5 | 3 | 0 | 0.546875 |
| stream_L2_D1_slack3:timed:t23:round1:loaded | 23 | 12 | 5 | 3 | 0 | 0 |
| stream_L2_D1_slack3:timed:t43:round2:loaded | 43 | 12 | 5 | 3 | 0 | 0 |
| stream_L2_D3_slack0:timed:t0:initial | 0 | 12 | 5 | 3 | 0 | 0 |
| stream_L2_D3_slack0:timed:t23:round1:loaded | 23 | 12 | 5 | 3 | 0 | 0 |
| stream_L2_D3_slack0:timed:t43:round2:loaded | 43 | 12 | 5 | 3 | 0 | 0 |
| stream_L4_D1_slack3:timed:t0:initial | 0 | 8 | 5 | 3 | 0 | 1.68828 |
| stream_L4_D1_slack3:timed:t23:round1:loaded | 23 | 11 | 7 | 4 | 0 | 0 |
| stream_L4_D1_slack3:timed:t43:round2:loaded | 43 | 11 | 7 | 4 | 0 | 0 |
| stream_L4_D3_slack0:timed:t0:initial | 0 | 7 | 5 | 3 | 0 | 0 |
| stream_L4_D3_slack0:timed:t23:round1:loaded | 23 | 9 | 7 | 4 | 0 | 0 |
| stream_L4_D3_slack0:timed:t43:round2:loaded | 43 | 9 | 7 | 4 | 0 | 0 |

2/8/32统计、每个候选全部成对成本和输入哈希见 analysis.json 及原始目录。未来为显式取消/反转/抖动压力分布，不是现场概率。

多个时间段相关；每个 tick 只探测第一个待路由盘。其他重复组经验regret仍有经验最小值偏差；不作总体置信结论。即时前缀相同但保留条件见证不同的干预仍保留原ID，样本价值相同也不删标签。
