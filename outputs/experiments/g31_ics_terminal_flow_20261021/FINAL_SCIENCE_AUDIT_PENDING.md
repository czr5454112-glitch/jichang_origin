# Final science audit — prepared, pending full closure

`final_science_audit_004.py` 保留历史文件名，内容已按显式 `--source-manifest`、`--workflow` 绑定，适用于登记的 workflow005。没有执行最终科学汇总；不存在基于未闭合 005 结果的效果结论。

驱动从 registration 的 stages 中只解析 bridge、bins、period、predictor 四个完整 DEV 块；不读 predecessor003、短 export gate 或 TRAIN 结果。四父 2201–2204、七方法、28 个 run 都必须有正式 closed receipt、worker 等值绑定和完整 59400 端点轨迹。方法合同、固定比较轴、输入/native/source/model 等绑定缺失或改变即拒绝完成标记。

六种逐袋配对各四父，共 24 对：C00→C10、C00→TF-current、TF-current→TF-B1-60、TF-B1-60→TF-B1-300、TF-B1-300→TF-B1-300-replan300、TF-B1-300→TF-predictor。campaign.evaluate 原有的 24 对结构比较另存一份；其中 TF-B1-60 的结构参考为 C10，不冒充本报告的 TF-current→TF-B1-60 信息增量比较。

输出保留每对全部 28,506 件行李的有方向完成/迟到损害、双方未完成与尚未到达；按原始 origin 汇总本地服务。预测升级对还保存实际订单与动作差异，区分同公开状态/菜单动作变化和已经分叉的闭环状态变化。各 run 的独立计划、计划项、订单、提交、接受、接收分母分别计数，保留 ordinary/extra 分类、失败、在途删失、多盘退化、反向与来源随访。

行为和计划链复用冻结 audit 的纯入口，一次流式决策扫描供行为/计划/时间统计。所有窗口内轨迹决策（含 HOLD 和 C00）都必须与决策流的唯一 ID、时间、owner、公开观察引用、catalog 和请求动作一致，并通过 digest/time/owner 流式连接 observation；额外窗口内决策、重复或缺失均拒绝完成标记。时间排序复用冻结 timing audit 的公式与纯 helper；无法重建当前 pending claims 的样本明确排除排序分母。完整 ACK 从不打开。`solve_seconds` 仅按 unique plan 计原始求解耗时；回调耗时及 stage scope 直接保留 worker.policy_timing，其 catalogue、submission、native、export 排除范围不会被省略，也不认证完整请求 100 ms。

所有冻结 source bytes 在入口和出口重查；入口 imports 必须来自该冻结树。分析驱动在入口绑定自身 SHA256，结束时必须与入口一致；每个 run 的十个实际消费文件（含 arrival support contract 和 receipts）在读取前绑定，结束再次核验。中间生成的报告也在最终引用前验证 SHA256。结果文件拒绝覆写。完整逐袋报告为紧凑 JSON gzip（mtime=0，allow_nan=false），摘要不含 per_bag 列表，均附 SHA256；单文件必须小于 95,000,000 字节。若中断或校验失败，只有 in_progress 标记和部分文件，不能当作完整科学结果；只有 `COMPLETE.json` 绑定 `final_science_report.json` 才确认全部审计闭合。

四父来自同一历史模板的派生场景，不是四个独立机场日；重复业务 ID 按 parent-bag 计数。平均收益绝不覆盖任一父的服务门槛拒绝，也不会自动批准晋级、保护接管、R1 或 TEST。

检查命令（无 `--execute` 时仅报告 pending/ready，不产科学报告、不启动 native）：

```powershell
C:/PROGRAMING/python3.11.9/python.exe outputs/experiments/g31_ics_terminal_flow_20261021/final_science_audit_004.py --source-manifest outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005/source_manifest.json --workflow outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_005/registration.json
```

由主代理在四块全部正式闭合后调用同一命令，并加：

```powershell
--execute --output-dir outputs/experiments/g31_ics_terminal_flow_20261021/final_science_005_001
```

验证：独立复核后 `test_final_science_audit.py` 的 16 项纯测试通过，JUnit 见 `final_science_pure_tests_004.xml`，覆盖 28 run／24 pair 完整矩阵、生产者修改拒绝、重复／缺失决策、全部 HOLD 观察校验、实际订单差异和十进制发布上限。workflow005 的 check-only 冒烟返回四块未登记、science_executed=false、native_starts=0；这不是对 005 的科学执行。旧 preparation receipt 保留当时身份，新的审阅 receipt 绑定本次修订。未修改任何冻结源。
