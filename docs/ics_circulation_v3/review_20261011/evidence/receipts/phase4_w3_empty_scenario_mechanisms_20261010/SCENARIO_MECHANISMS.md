# 公共情景方法完整配对与机制例证

固定全36条流×三个种子，同时对point和legacy配对，共216项。例证选择规则已在完整summary出现前落盘；这是事后解释，不是重新训练、调先验或独立确认。

| reference | seed | n | delta J | delta on time | better/equal/worse |
|---|---|---:|---:|---:|---:|
| point | scenario8_s17 | 36 | +14.2 | +1 | 3/20/13 |
| point | scenario8_s29 | 36 | -6.2 | +2 | 3/30/3 |
| point | scenario8_s43 | 36 | -3.0 | +1 | 2/34/0 |
| legacy | scenario8_s17 | 36 | +16.3 | +0 | 2/20/14 |
| legacy | scenario8_s29 | 36 | -4.1 | +1 | 2/31/3 |
| legacy | scenario8_s43 | 36 | -0.9 | +0 | 1/35/0 |

最大三种子成本跨度：s3_t6，16.9 J。全部36条跨度均保留。每个种子的极值即使为零或同号也保留，不强行命名正/负例。

| role | unit | seed | delta versus point |
|---|---|---|---:|
| minimum_delta | s2_t1 | scenario8_s17 | -2.8 |
| maximum_delta | s2_t0 | scenario8_s17 | +3.0 |
| minimum_delta | s3_t6 | scenario8_s29 | -15.9 |
| maximum_delta | s3_t0 | scenario8_s29 | +4.0 |
| minimum_delta | s2_t8 | scenario8_s43 | -2.1 |
| maximum_delta | s0_t0 | scenario8_s43 | +0.0 |
| maximum_seed_spread | s3_t6 | scenario8_s17 | +1.0 |
| maximum_seed_spread | s3_t6 | scenario8_s29 | -15.9 |
| maximum_seed_spread | s3_t6 | scenario8_s43 | +0.0 |

绑定220份原件，SHA变化0，检查260项/错误0。point与原factorial timed/fewest的36次两端点完整物理、route/slow记录逐项验证。

analysis.json保存每个首动作分歧的公开snapshot SHA、point预测、完整候选顺序、每候选八样本成本、八情景取消/扰动组成、重复权重与实际物理trace。样本均值是未校准prior下的估计，不能称真实未来条件期望或概率保证。

逐例物理链另存PHYSICAL_CHAINS.md；所有正负分母保留，不能将选择出的极值当总体表现。
