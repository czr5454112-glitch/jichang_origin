# 固定机场图上的新循环 OD 研究合同

新业务版本为 `g31.foundation.airport_cyclic_od.v1`，新运行方案为 `g31.foundation.airport_cyclic_od_calibration.v1`。这不是原 C00/C10 场景的修复或重新评级。原 150 秒 C00/C10 负结果、原输入、源工作簿和归档保持原样。

## 变更与守恒

静态业务投影只作以下同角色替换：入口 92→95；卸点 99/101/103/106/108/110→114/116/118/120/122/124。共保留 28,506 个原业务身份、360 个完整 flight parent。4,001 件改变 destination、3,102 件改变 origin，两者重叠 430 件，合计 6,673 件 OD 字段变化。入口 92 的三个完整源 lane 均整体替换，不拆组删件。

全部到达、deadline/STD、storage53、释放时间、加载/卸载/hold 服务及其他 job 字段不变。全部非 job 输入字段不变，包括 151 节点、227 条有向边、97→98 的零容量、所有容量/headway/FIFO/权限、22 个托盘及其原初始位置。候选具有静态正容量路径与返回使用入口的回路；这不证明有限缓冲吞吐、无 gridlock、时限或逐件改善。

冻结身份：

| 内容 | SHA-256 |
|---|---|
| 旧协议完整输入 | `ffe8a52c4ad2b6a841e800e293baa3333b97cd128e6dc3157c9801f828a12589` |
| 新协议完整输入 | `5a99b213c855e60b94a423a816ea80a2f23acb04a651ae418a21f9056e59edcf` |
| 新业务集合 | `cedfdbfb91c029dbe6db6552be8c4d0aad67a3ad78492819de840e22788e5006` |
| 不变的非业务字段 | `2a1bfb818e79362e0f14dbdd37934e99e64ba2f84ab75ddd3c2ce9128cc211ca` |
| 新完整 crosswalk | `b2a1cf3a0d46ce0838e85d19abbb04f6a2007bf38101d356fd9d56e0d72cb03f` |
| 完整逐件/parent/lane 审计 | `774492c3e25e3a7553a9c407c23e291a5d89a12ae561596cde69fe43a2547aab` |

`foundation_airport_feasible_domain.py` 从原登记输入构造新副本并逐件验证。准备输出包括完整输入、`business_contract.json`、`business_audit.json.gz`、`business_crosswalk.json.gz` 和旧输入 manifest。审计保存全部变更 ID、原/新 OD、原任务 ID、parent key、所有 360 个 parent 的业务成员和全部 standard lane 成员。该审计与原始逐件输入只用于离线来源验证，不进入 actor。

## 公开预测映射

映射版本为 `airport151_std8_pushforward92to95_gtc3_v2`，schema 为 `g31.foundation.airport_role_mapping.v2`。它将旧静态 std8 均匀先验按 92→95 推送：legacy_start_0/1/2/3/4/5 的 95 权重为 2/8，其余六个使用 standard loader 各 1/8；legacy_start_53 仍均匀分到三个 GTC 入口。92 不再是预测注入目标。

这只是预登记的共同研究先验，不是现场航班提前分配，也不读取完整历史组大小。未来需求均值总量守恒，源区域未知时相应节点保持 unknown，节点区间仍为 unknown，不能把相关拆分当独立校准区间。B1 模型、context、time basis、训练截断及 43,200 秒冻结时点保持原样；新输出显式携带新业务 SHA、映射版本和源预测摘要。

## 被动公开观察采集

新两分支使用同一机场协议 wrapper、真实 ProtocolClient、原提交/重试/ACK 处理。C00 的 planner 直接调用原 `transfer_candidates`；C10 在 57,660 秒前返回相同原规则结果，之后才允许原保守航班预置 planner。collector 的显式身份纳入 controller config，业务和 native 不因采集创建新动作。

`g31.foundation.airport_policy_observation.v1` 仅保存 43,200–59,400 秒之间真正传入 planner 的 observation/options 和真正返回的 decision，包括 residual 调用。返回原 decision 对象，不增加 native 查询、不读全局结果、不补造标签。输出 `policy_observations.jsonl.gz` 使用逐条独立 gzip member，硬退出前完整成员前缀可保留；未完成的尾成员不能冒称完整记录。正常退出另有记录数、owner、时间范围和文件 SHA 回执。

这些数据是合法观察来源，尚不是带有真实条件结果的训练样本。它们不证明 RL readiness，也不能从未执行候选的评分推出真实奖励。

## 单次校准与 CLI

先登记新域 C00 单分支校准，hard 300 秒、soft 240 秒、自动重试 0 次。仍从物理 0 开始，同一 session 连续 warmup 到 57,600 秒，再到 58,200/58,800/59,400 秒；原业务输入全日 horizon 86,400 秒不变，跨窗任务、托盘、请求和 controller 状态均保留。闭合到 59,400 只是校准完成，不是全日 28,506 件完成。

准备（不启动 native）：

```powershell
& C:\PROGRAMING\python3.11.9\python.exe -m scripts.experiments.g31_ics_circulation.foundation_airport_feasible_campaign --prepare --branch C00 --output outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/C00_cyclic_od_001
```

由统一预算登记者启动：

```powershell
& C:\PROGRAMING\python3.11.9\python.exe -m scripts.experiments.g31_ics_circulation.foundation_airport_feasible_campaign --launch --output outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/C00_cyclic_od_001
```

C10 必须等待真实 C00 结果后再决定，并显式传入该新域闭合 `receipt.json`。旧 C00 或 timeout 不能作为准备凭据；没有自动运行 C10 的后继逻辑。两分支使用同字节业务输入、相同 warmup 和采集规则，最终配对仍需相同真实 warmup state SHA、终点和完整业务集合。所有不完整件保留 unknown，逐件比较容差仍为 0。

本轮准备和纯测试不包含 native 吞吐结论、跨 owner 入站账户适配闭合、动作价值模型训练或四组实验结果。
