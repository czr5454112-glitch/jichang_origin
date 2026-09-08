# 调度器 V2 的合成复核

本目录验证 DH 旧、新解析器的受控选择与 staged campaign 阶段控制。它不新增数值实验，也不证明物理轨迹正确。所有进程启动与任务池调用均被 mock；没有调用 Java/C++ 仿真。

`check_orchestrator_parser_v2.py` 用两份明确标为合成数据的 CSV，调用实际旧、新 `normalize` 及调度器的 gzip、身份和复用检查。旧版本验证完整人口；V2 验证含 `N/A` 的未完成人口，保留完整分母且两种 THT 均为 null。旧解析器处理同一 `N/A` 输入仍失败，作为负控。其余 trace/summary 等仅为带标记的哈希占位数据，不作为事件或轨迹证据。

复核还包括：错误路径或 SHA、非 DH 使用 DH V2、既有失败原生目录不被重启、原三个已完成 DH 绑定旧解析器、恢复单元只替换坐标对应的 ID/目录而不增加第 1761 格、输出布局检查不放宽，以及 16/8/1760 阶段失败和正常 2× 前置门会阻止后续派发。恢复负控会分别篡改原生副本字节、旧 status 副本、命令、源 spec、解析器/helper 身份及相互绑定的恢复记录；只 mock 原 source validator 的前置返回，新的副本与 provenance 检查实际执行。

从仓库根运行：

```powershell
C:\PROGRAMING\python3.11.9\python.exe outputs/evidence/paper_suite_20260907/orchestrator_parser_v2_qa/check_orchestrator_parser_v2.py
```

脚本在 `build/paper_suite_orchestrator_parser_v2_qa/<唯一目录>` 创建合成证据，不改正式结果。`verification.json` 记录最终脚本及解析器 SHA、49 项检查和原始调度器保护哈希。其中最后四项还只读载入真正的 V5 计划，核对其 SHA、16/8/1760 阶段、3 个旧解析器与 117 个 V2 绑定、单个恢复坐标；不将合成计划冒称正式冻结计划。

`verify_real_mixed_DH.py` 另对 V5 代表阶段的三个原已完成 DH 和一个恢复 DH 各运行一次真实 `verify_cell`。它实际调用恢复 helper 的原 source validator、重新计算人口指标、核查压缩档和 provenance，且要求 normalized 字节不变。结果见 `real_mixed_DH_verification.json`；随后运行的 master `--check-only` 完整只读前置检查见 `master_precheck.json`。此脚本拒绝覆盖已有记录，未启动真实 pool 或 native，四格核验不代表全部 1760 格已完成。
