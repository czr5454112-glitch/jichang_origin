# 缩减矩阵主控 V3 复核

V3 只绑定冻结的 V6 计划：基础 480 格保持不变，故障为场景 `[1,2,9,14]`、共同种子 `[104729,130363,155921]` 的 96 格，总计 576。新范围合同决定当前实验数量；旧逐格协议继续规定物理和时间口径。所有保留单元与父 V5 的完整条目相同，包括输入、输出、运行器及 SHA。

主控执行顺序为：基础代表 16 格复核 → 正常 2× 等价门 → 全部基础 480 格 → 故障代表 8 格复核 → 全部故障 96 格。任何阶段失败都禁止后续派发。沿用同一个冻结 pool V2、4 workers、默认无 wall timeout、逐格复用验收和旧证据禁止覆盖规则。有效终态可以包含未完成人口，其 THT 仍由原 full-population-only 口径处理。

`verification.json` 为 31 项检查结果。`check_reduced_campaign_v3.py` 以 mock pool 验证顺序、失败、正常 2× 前置门、别人的锁必须保留等边界，并只读校验真实 V6 的 576 格、范围合同 SHA、父 V5 SHA 和保留单元不变。它没有启动仿真、真实任务池或进程控制。

`master_precheck.json` 是实际 V3 `--check-only` 的结果：阶段规模 `[16,480,8,96]`、原 initial4 池就绪、正常 2× 等价证据就绪，均通过。此检查仅读现有证据，不重新模拟或解压重算全部人口，也不表示 576 个实验已经完成。

从仓库根可重跑合成检查，产物进入新的 build QA 目录：

```powershell
C:\PROGRAMING\python3.11.9\python.exe outputs/evidence/paper_suite_20260907/reduced_campaign_v3_qa/check_reduced_campaign_v3.py
```

旧 master V2 和 pool V2 字节保持不变。旧主控的暂停、等待子进程自然完成、仅终止主控及自有旧锁归档由根代理另行处理；本目录没有执行这些操作。
