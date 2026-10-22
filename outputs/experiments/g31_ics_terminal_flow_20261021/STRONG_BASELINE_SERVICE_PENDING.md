# 同B1强基线逐袋补充审计：已准备，未执行

`strong_baseline_service_audit_005.py` 独立生成四父 C10→TF-B1-60 的完整逐袋服务比较，补足原24逐袋对之外的同B1图分配轴；不修改原 final_science 报告、24对定义或两张图。

默认check-only。`--execute` 必须全部28个005 DEV run正式closed，来源/父输入/59400端点/7200激活点/方法合同及完整日志均通过冻结005检查。source005 SHA `22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef`、workflow005 SHA `1509684b0eaa8433795343d508142654f90927ef70553783c272f343205aa30d` 与共享支持脚本 SHA 均固定。所有run的plan/receipt/worker/trajectory，以及实际比较八run的terminal log和全部计划文件依赖在消费前绑定，结束重查。服务计算只导入冻结005的 `foundation_airport_terminal_service_audit`，没有raw observations或owner ACK读取，没有native启动、模型拟合或预算修改。

每对保留全部28,506件及双未完成/尚未到达，实际完成/迟到方向和原服务门槛逐项呈现。输出四份紧凑gzip逐袋文件、`strong_baseline_service_report.json`及最后的`COMPLETE.json`。平均收益不能覆盖某父服务拒绝。四父同历史模板派生，重复ID按parent-bag计数；不宣称四个独立机场日。失败或中断仅保留pending/部分文件，不能算完整审计。

主代理在完成条件满足后通过已登记offline wrapper调用以下子任务；不要另行并发启动：

```powershell
C:/PROGRAMING/python3.11.9/python.exe -B outputs/experiments/g31_ics_terminal_flow_20261021/strong_baseline_service_audit_005.py --source-manifest outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005/source_manifest.json --workflow outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/terminal_flow/workflow_005/registration.json --execute --output-dir outputs/experiments/g31_ics_terminal_flow_20261021/strong_baseline_service_005_001
```

建议wrapper hard allowance为300秒，证据预留134,217,728字节（128MiB）；脚本自身在完成前检查输出累计大小低于此上界。单文件另受95,000,000字节发布上限约束。

准备验证：`--help`成功；12项有限synthetic纯测试通过（`strong_baseline_pure_tests_002.xml`），包括28run缺失/未闭合、固定配对轴、完整唯一人口、删失及损害定义、输入hash变化、生产者执行中变化不生成COMPLETE、四父合成成功输出。测试目录显式命名`outputs/strong_baseline005_pure_synthetic_test_002`，不作为真实科学证据。未对真实005执行此审计。

驱动SHA256：`17dfb93495dcf3bccdc26d25339e5b4b33e47337d326dfee10764380358baa5b`。
