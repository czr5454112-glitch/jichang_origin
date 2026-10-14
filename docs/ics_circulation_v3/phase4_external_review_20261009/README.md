# 本轮交付内容

本包对应冻结提交 `030493a399cdcac3fc005fe2f2cd8ec30fc96277` 的源码阅读审核。

- `ICS_V3_030493_audit_and_phase4_plan_20261009.md`：独立审核、需求完成度、问题分级、五个有依赖的工作包和 Codex 执行指令。
- `ics_v3_review_probes_20261009.py`：五项可运行诊断，用于在冻结副本中检验单见证遗漏、释放预测接口、后缀更新、场景约束活跃性和实际动作别名。
- `source_review_manifest.json`：实际阅读范围、永久链接、证据等级及本轮未执行事项。
- `authoring_validation.json`：交付文件语法/存在性检查，不是原仓库测试结果。

## 重要范围

本轮实际阅读了冻结代码和指定原始结果片段，但没有在写作环境重跑原仓库的 238 项测试或整套实验。报告不把实现方保存的运行结果当作本轮重新计算的结果。诊断脚本仅做了 Python 语法检查，尚未在原仓库执行。

在独立冻结副本运行探针，输出路径必须为新文件：

```powershell
python .\ics_v3_review_probes_20261009.py --repo-root C:\TEMP\ics_v3_frozen_copy --output C:\TEMP\ics_v3_probe_run_001.json
```

探针没有网络访问、训练和历史结果改写。`diagnostic_exposed=true` 表示暴露待解决问题，不是应维持的 PASS 条件。修复后复验用 `--allow-modified` 并保留新版本信息；接口变化时相应更新探针。

本包不包含原仓库源码、原论文、原始全量实验或依赖安装包。
