# 本包内容与复现

本包是2026-10-11拿到用户V3上传ZIP后的真实执行审查和G31整合计划，不是已经修改好的生产仓库。

先读 `ICS_V3_G31_executed_audit_and_integration_plan_20261011.md`；交给Codex执行时配合 `ICS_V3_G31_Codex_next_stage_20261011.md`。`NOVELTY_LEDGER_20261011.md`用于阶段性创新判断，当前新主张均待验证。

`evidence/release_run_001/`保留实际1519项V3回归的结果、JUnit、原runner和源码前后摘要。`evidence/probes/portable_run_001.json`保留3项确定问题与其他边界的原始定向观测。默认probe exit 0表示探针执行完毕，不表示没有缺陷。

复现新反例：

```bash
python reproduce_audit_probes.py --root /path/to/jichang_origin --output new_observations.json
```

修复后可追加`--require-fixed`，同时人工检查模型拒绝的原因和范围。当前源码会报告N1/N2/N3；本包没有修改它们。

`evidence/probes/attempt_001`等为先前开发尝试的逐件保留，其脚本可能依赖本轮本地root.txt，不作为跨环境入口；可移植入口是本包顶层的reproduce_audit_probes.py。重复的诊断不计独立业务样本。

本包不含整个V3仓库、133MB恢复fixture、成熟G31源码包、全部原业务raw、230MB证书状态或未提交C++修改。原ZIP已足够复现已执行的V3发布回归；G31整合执行和原44袋恢复仍需主报告列明的对应资源。

所有source/hash身份检查、AST扫描、实际测试、逐行阅读的范围分开列出；没有全仓逐行审核、成熟G31原生运行、新系统性能或现场验收的隐含声明。
