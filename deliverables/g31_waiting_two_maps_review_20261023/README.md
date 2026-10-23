# G31 双地图等待评分审阅包

基于 `9f23c25a631786ad4c1f47c442d72dcfb3ac098f` 的独立审阅分支；默认 `legacy` 保持不变。
请从 [REVIEW_PROMPT.md](REVIEW_PROMPT.md) 开始审阅。源码修改仍在原仓库路径，报告和机器审计未移动。

本次保留成熟 G31/S4/J2/PIBT，仅增加可关闭的拥堵评分候选。旧 G31 已有 ETA 日历等待，正式可见性原已开启。双方均不新增线路容量，不运行空托盘。
两图使用同一原始 28,506 件业务／43,603 个运输段；南宁是 OD 投影。固定参数、不为 map2 重新调参，是地图迁移验证，不是两份独立客流样本或普遍优势证明。

## 各图完整七臂结果

单位为秒；每行使用全部 43,603 段。规范起点与实际释放起点分别列出，不能混为同一个比较。

| 地图 | 实验臂 | 完成段 | 规范到达→完成均值 | 实际释放→完成均值 | 规范 P95 | EBS 因果异常业务 |
|---|---|---:|---:|---:|---:|---:|
| nanning | Java | 43,603 | 3227.992 | 292.920 | 17285.127 | 1,102 |
| nanning | G31_legacy | 43,603 | 454.967 | 454.967 | 2064.523 | 12 |
| nanning | G31_calendar | 43,603 | 440.980 | 440.980 | 1952.090 | 9 |
| nanning | G31_flow | 43,603 | 447.226 | 447.226 | 2018.896 | 10 |
| nanning | G31_legacy_same_HCA | 43,603 | 3159.306 | 224.235 | 17264.534 | 1,102 |
| nanning | G31_calendar_same_HCA | 43,603 | 3158.378 | 223.306 | 17261.114 | 1,102 |
| nanning | G31_flow_same_HCA | 43,603 | 3158.422 | 223.351 | 17261.114 | 1,102 |
| map2 | Java | 43,603 | 301.980 | 194.643 | 1055.900 | 0 |
| map2 | G31_legacy | 43,603 | 193.523 | 193.523 | 340.501 | 0 |
| map2 | G31_calendar | 43,603 | 193.747 | 193.747 | 340.715 | 0 |
| map2 | G31_flow | 43,603 | 193.771 | 193.771 | 340.664 | 0 |
| map2 | G31_legacy_same_HCA | 43,603 | 276.925 | 169.587 | 1016.851 | 0 |
| map2 | G31_calendar_same_HCA | 43,603 | 276.897 | 169.559 | 1016.851 | 0 |
| map2 | G31_flow_same_HCA | 43,603 | 276.897 | 169.559 | 1016.851 | 0 |

原释放各臂具有各自源策略；同 Java 释放臂才共享实际 generator release。表中同释放臂的规范耗时仍包含 Java 源生成延迟，不能误称实际释放后的耗时。

- nanning 原释放：相对旧 G31，eta_calendar 均值变化 -3.0743%，eta_flow -1.7013%（正数变慢，负数变快）。
  同 Java 释放的实际释放→完成均值：legacy 224.234833 秒、calendar 223.305945 秒、flow 223.350693 秒。
  calendar 相对 Java 的 292.920372 秒低 23.7656%；相对同释放旧 G31 仅低 0.41425%。算法和执行边界差异仍保留，不能把全部优势归因于此次评分。
- map2 原释放：相对旧 G31，eta_calendar 均值变化 +0.1160%，eta_flow +0.1280%（正数变慢，负数变快）。
  同 Java 释放的实际释放→完成均值：legacy 169.587003 秒、calendar 169.559224 秒、flow 169.559224 秒。
  calendar 相对 Java 的 194.642662 秒低 12.8869%；相对同释放旧 G31 仅低 0.01638%。算法和执行边界差异仍保留，不能把全部优势归因于此次评分。

**两图原释放下的纯日历候选收益方向不一致。** 南宁的改善没有在 map2 原释放工况中复现；默认继续保留 legacy，不按单张图或单一均值升级候选。

各图需分别判断收益、尾部和误差，不把南宁结论移植为 map2 结论。出现 EBS 因果异常时，业务端到端数字仅是观察值；主要结论使用完整独立运输段分母。

## 原路径报告与审计

- nanning：[报告](../../outputs/experiments/g31_feng_alignment_20261023/REPORT.md)、[七臂比较](../../outputs/experiments/g31_feng_alignment_20261023/final_audit_001/audit.json)、[请求差异](../../outputs/experiments/g31_feng_alignment_20261023/request_audit_001/audit.json)、[报告数据](../../outputs/experiments/g31_feng_alignment_20261023/report_data_002/report_data.json)。
- map2：[报告](../../outputs/experiments/g31_feng_alignment_map2_20261023/REPORT.md)、[七臂比较](../../outputs/experiments/g31_feng_alignment_map2_20261023/final_audit_001/audit.json)、[请求差异](../../outputs/experiments/g31_feng_alignment_map2_20261023/request_audit_001/audit.json)、[报告数据](../../outputs/experiments/g31_feng_alignment_map2_20261023/report_data_001/report_data.json)。

最终 Python 回归为同一组五个文件 33 项通过：[最终回执](../../outputs/experiments/g31_feng_alignment_map2_20261023/python_regressions_002.xml)。首次回执中的两个失败来自 sandbox 临时目录的 `os.replace` WinError 5；将 basetemp 改为工作区后原样重跑通过，没有为通过测试修改代码。首次回执也保留供核查，不能把该环境失败混入算法实验结果。

## 包含的证据与明确缺项

每图一个 ZIP，内部保留仓库相对路径：七臂完整 segments/business 账本、六个 G31 请求、canonical、地图和任务源、Java release/lifecycle/output/starttime/routes/run_status，以及公开的 summary/manifest/audit。Java 自身没有 G31 request.json.gz，原始命令由 run_status 等记录。
map2 ZIP 另含 15 个原 Java 源文件的精确字节快照及两份外部原地图/任务输入。外部输入在 ZIP 中声明为虚拟 repo-relative source/original_inputs 路径，未覆盖仓库镜像；换行差异保留在原 source manifest。
仅 nanning ZIP 包含一份两图共用的原生 Windows CPython 3.11 模块。完整 native_payload.json.gz 未打包：每份的 SHA256、字节数和明确未包含状态列在 PUBLICATION_MANIFEST.json。没有伪称归档包含完整原生大 JSON、完整事件带或全部历史构建树；原有回归回执可供审阅，但重新逐字段对照历史 native payload 需要原文件。
当前源码由基线提交加本次明确列出的修改重建；每次运行的原始 source/binary hash 保留在 manifest。少量运行时 harness 快照随 ZIP 保留，以解释后续通用脚本新增 map2 参数支持造成的哈希变化。本地论文 PDF 原文未加入公开包。

- [nanning 全量证据](nanning_full_evidence.zip)：33.25 MiB，73 个文件。
- [map2 全量证据](map2_full_evidence.zip)：27.53 MiB，95 个文件。

## 校验与发布文件清单

从仓库根目录运行（无需解压、无需外部原路径、不会启动模拟器）：

```text
python scripts/experiments/g31_feng_alignment/build_review_bundle.py verify
```

verify 校验所有显式发布文件的 SHA256/字节数、ZIP 完整成员集合与每个成员哈希，并直接读取 ZIP 全量 canonical+segments 重算两图各七臂指标和业务账本，对照公开 summary。
[PUBLICATION_MANIFEST.json](PUBLICATION_MANIFEST.json) 的 publication_paths 是本次允许发布的逐文件清单，不能用全目录 git add 替代。为避免循环哈希，manifest 自身单列而不对自身计算内嵌最终 SHA；其余发布文件均有 SHA/大小。Git 提交自身提供完整内容身份。
ZIP 保留原始字节，若检出环境改变公开源码的换行，严格哈希可能失败；需按清单恢复本次发布字节后再复核。
