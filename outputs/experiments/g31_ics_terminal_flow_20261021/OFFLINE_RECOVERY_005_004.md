# 离线审计路径修复及恢复004

source005 的32场原生运行全部闭合。离线执行003首项在读取完整TRAIN块时，把数据校准文件定位到冻结源码内部的 outputs 路径，因文件不存在退出。正式科学输出目录尚未建立，其余十项未启动。直接子进程和Windows Job树均确认退出，原ledger已关闭runner并计85.730185秒；native starts仍54。

修复仅在完整TRAIN离线驱动中，将冻结验证器的 CYCLE 临时绑定到哈希固定的 workflow 所在实际数据周期，验证结束或异常时恢复原值。原冻结验证逻辑、校准哈希检查和源文件均保留。旧驱动/测试保存在 full_train_path_history_001，失败执行保存在 offline_budget_execution_005_003。

26项纯测试通过，包括正确数据路径及异常恢复；真实两个TRAIN的 metadata-only 预检通过。recovery004保留原11任务、全部时限、内存和证据上限，只更新该驱动绑定。原任务正式输出目录全部仍不存在，因此沿用原输出目的地；wrapper使用全新的 offline_budget_execution_005_004。

ready004 SHA：`7e95527ab0560a608a45a53b16b5097aba2a09a934095426070c8236eb9ffc16`。

启动命令（本记录创建时已启动，不可重复执行）：

```text
python -B outputs/terminal_flow_offline_budget.py --spec outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_spec_005_ready_004.json --execute --output outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_execution_005_004
```

此次预检原账本累计59972.928112秒，历史保守预留37945.152683秒，未覆盖间隔612.210911秒，新增离线预留13020秒；总预留111550.291706秒，距原172800秒上限剩61249.708294秒。证据16,420,041,103字节，新增预留1,912,602,624字节，空闲136,776,732,672字节。运行中继续按原预算检查，无预算重置。

此记录不表示审计已成功或服务门槛通过。完成状态须核对EXECUTED、每个任务COMPLETE以及原ledger真实runner_close；失败保留证据并停止自动重试。

后续状态（2026-10-22 04:32 UTC）：004 已完成完整 TRAIN 时间尺度与 DEV 粒度分析；final_science 达到原 3600 秒时限后停止，进程树与原账本均已闭合，实际计费 5954.098387 秒。详见 `offline_budget_failure_closure_review_005_004.json`。11 份完整逐运行报告保留，未被当作完整最终审计。

续行 005 已独立登记并启动，spec 为 `offline_budget_spec_005_ready_005.json`，SHA256 `eb247ca57630e8905e6ad237ea071c44aaa6c9e2f0cc524d2cecaa64a067ca17`。它复用已校验的 11 份报告，补余下 17 场并执行后续科学汇总；不重跑前两个完成任务，不新增 native。原账本、源码、模型、物理/服务合同不变。新 final_science 上限为 14400 秒，九任务合计预留 20820 秒，另为四场 600 秒分箱原生对照及审计预留 13200 秒；预检后总预算余量 34155.082614 秒。该余量包含保守历史与未覆盖间隔预留。

下列命令已启动，仅用于识别当前执行，不能重复运行：

```text
python -B outputs/terminal_flow_offline_resume005.py --spec outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_spec_005_ready_005.json --execute --output outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_execution_005_005
```
