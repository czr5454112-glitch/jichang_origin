# 005 分箱敏感性复核：入口已准备，等待四父细网格闭合

`streaming_granularity_audit_005.py` 仅用于 workflow005 的四个完整 DEV `TF-B1-60` 运行（P2201–P2204）。当前只完成辅助脚本与纯测试，没有运行完整复核，没有新增 native，也没有生成分箱效果结论。旧 002／003 的 422 机会结果保留原有身份和含义，不与新的 005 结果合并。

默认模式只检查登记与闭合状态。入口按 workflow 的 bridge 块找到四个运行，验证 source005、方法、59400 完整端点、7200 激活点、正式 closed receipt、worker 等值与完整轨迹。四父缺一或尚未闭合时，`--execute` 拒绝创建结果目录。TEST、其他 source、短窗口、粗网格来源和已经校准的 predictor 来源均不能进入。

每条窗口内轨迹决策必须唯一匹配 decision stream 的 ID、时间、owner、公开观察引用、catalog 和请求动作。观察采用单调流式 join，仅保留当前时刻的 owner 记录，并重算 digest、核对时间和 owner。完整 owner ACK、native snapshot、calls 都不读取。轨迹只用于闭合与身份校验，不使用其 MC／服务标签选择参数。原始 `recorded_decisions` 包括整个保存流；`[7200,59400)` 之外的记录另计 `excluded_outside_registered_window`，包括终点边界决策，避免把未纳入完整轨迹的终点操作并入重放分母。

使用实际 callback 保存、已经被 actor 消费的 fine B1 forecast；核对外层 actor SHA256、观察 SHA256、owner、相对时间、绝对 callback 时间、训练成熟／模型可用时间和实际 plan receipt 时间。只对保存的 60 秒质量做重分箱，绝不再查询 B1 CDF、未来真值或另拟合参数。

四模式为 60／300／600／near_fine。逐机会采用冻结 `transport_campaign.offline_granularity` 相同顺序和纯算法：同一公开观察、同一优先任务基线、同一真实可用盘菜单、同一配置、600 秒库存投影、1800 秒需求范围、60 秒重算周期、2 秒命令延时；每种表示从空的离线 policy state 重放。缺少 `receiver_claims_deducted` 证据直接报错；非零预留明确计入 `excluded_uncredited_claim_opportunities`，不猜成零。优先任务尚未清空单独排除。

输出同时记录以下三类差异，均相对 60 秒表示：

- `first_action_changes_vs_60`：比较首个候选的 action type、source、destination、真实 tray identity。
- `total_quantity_changes_vs_60`：比较 `len(chosen)`。旧 `quantity_changes_vs_60` 字段保留相同含义，方便核对旧算法，但不把它解释为所有分配变化。
- `quantity_allocation_changes_vs_60`：比较全部 chosen 真实盘的 `(source,destination)` Counter，可识别总盘数相同、OD 分配不同的计划。plan ID、order ID 等元数据变化不计为分配变化。

每个 loader 的 600／1800 秒累计需求质量和已知／未知状态必须一致；已知质量差异超过 `1e-9` 即拒绝结果。ETA 落在粗分箱内部时，积分使用该表示的分段均匀质量，允许累计需求和动作变化，分别给出 count／平均绝对差／最大绝对差。此敏感性不是服务收益；同一场景重复机会也不是独立机场日。是否仍跳过 600 秒 native 必须由主代理查看新的完整证据后决定，脚本不自动替用户作此决定。

生产者包括本脚本和共享的 `final_science_audit_004.py` 支持文件，均在入口读取前绑定并在结束比较 SHA256。源、workflow、bridge、plan 依赖及每个 run 的八个实际消费文件也绑定并在完成前复核。输出拒绝覆写，单文件小于 95,000,000 字节；仅 `COMPLETE.json` 绑定最终报告才表示完整四父复核成功，中途失败留下的 pending／部分报告不能作为最终结果。

检查命令：

```powershell
C:/PROGRAMING/python3.11.9/python.exe outputs/experiments/g31_ics_terminal_flow_20261021/streaming_granularity_audit_005.py --source-manifest outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005/source_manifest.json --workflow outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_005/registration.json
```

收到四父 TF-B1-60 全部闭合通知后，主代理可使用同一命令加：

```powershell
--execute --output-dir outputs/experiments/g31_ics_terminal_flow_20261021/granularity_005_full_001
```

16 项纯测试通过，见 `granularity_pure_tests_002.xml`。测试包括一对实际加载冻结005算法的极小合成机会：无 claim 与非零 claim；新循环与冻结原函数的旧分母、旧 mode 字段和 ETA 质量统计逐字段相等。其他测试覆盖总量相同而 OD 分配不同、源/方法/时间范围限制、全部轨迹观察绑定、终点排除、生产者变化拒绝、质量／已知性改变拒绝、缺失和非法 claim 拒绝，以及四父完整性。测试没有使用实际 full DEV 保存观察、没有 native 启动或模型拟合。
