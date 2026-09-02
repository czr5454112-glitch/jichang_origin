# Feng-native CIE-DH 恢复交叉表

## 判定

`FENG_NATIVE_CIE_DH` 当前状态为 **`BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED`**。已恢复的 Feng Java 工程是 HCA 全路径调度器，不包含足以忠实实现 native CIE-DH 的状态机或决策代码。公共 C++ 执行器中的 CIE-DH/Tarău-local 实现是透明的 adapted baseline，但不是此处所说的 native 恢复。

## 机制交叉表

| 机制项 | native CIE-DH 所需契约 | 已恢复 Java HCA 中实际存在 | 恢复状态 | 实验后果 |
| --- | --- | --- | --- | --- |
| 决策粒度 | 路口/开关处的局部下一跳决策 | `Astar.research` 生成带约束的完整路线 | 不匹配 | 不能把 HCA 改名为 DH |
| 时间推进 | 0.2 秒位置级执行和状态更新 | `RUN.Main` 与 headless wrapper 按整数 epoch 调用调度 | 缺失 | 不能声称复现原生运动过程 |
| 位置状态 | 能区分路径上的 moving 与 stopped 行李 | `Node` 路线时窗、任务 passed/pass vertex 与全局 constraint | 缺失所需状态语义 | 无法从现有字段无歧义重建 DH 拥堵计数 |
| 局部拥堵范围 | 文献机制对应的局部观察/续接范围 | HCA 维护全局 `saved_routes` 与时空约束 | 不匹配 | 不得把全局预约信息泄漏给 adapted DH |
| HOLD | 明确的保持动作与触发条件 | 未找到对应标识符或分支 | 缺失 | 不得自行补写并称为原实现 |
| BTI | 原机制的 BTI 定义与更新 | 未找到对应标识符或分支 | 缺失 | 无法进行 native 参数冻结 |
| DDI | 原机制的 DDI 定义与更新 | 未找到对应标识符或分支 | 缺失 | 无法进行 native 参数冻结 |
| 拥堵系数 | moving/stopped 等系数的原始值与组合公式 | 未找到 DH scorer 或已披露系数 | 缺失 | 任何 1/2 等权重只能标为适配假设 |
| 故障 | 原 DH 的感知、绕行与恢复语义 | HCA 有全局故障边与重规划 | 仅 HCA 可用 | 不能外推为 native DH 故障能力 |
| 输出事件 | 释放、成功规划、路线和完成事件 | wrapper 可观测并导出 | HCA 可恢复 | 支持 HCA 回归，不足以恢复 DH |

## 搜索与调用证据

搜索覆盖独立原工程 `C:\PROGRAMING\czr004\jichang_origin\src` 和仓库冻结镜像 `legacy/jichang_origin_readonly/src` 的全部 Java 文件。两处均未命中 `CIE-DH`、去中心化标识、moving/stopped、HOLD/BTI/DDI 或带单位的 0.2 秒/200 ms 离散步长表达。

实际可跟踪的路由调用是 `Tasks.generate_tasks` → `ICS_PathFinding.ICS_path_finding` → `Astar.research`。该链条使用全局路线集合和约束表，属于 HCA；未发现另一条局部 DH 调用链。

## 允许与禁止的替代

允许继续做的工作：

- 在 P0 中重跑 Feng-native HCA，确认原工程可构建和结果可回归；
- 在 P1 公共执行器中，将 CIE-DH adapted 的自由流静态势与服务感知静态势做受控分解；
- 清楚记录 adapted scorer 的信息边界、权重与差异。

禁止的表述或操作：

- 把 `CIE_DH_REPLICA`、`FENG_DH` 或 Tarău-local adapted 输出写成 Feng-native；
- 用公共 C++ 执行器结果填充 P0 native DH 单元格；
- 因缺少源码而从 HCA 的全局 reservation/route 状态拼出一个“看起来像”DH 的版本；
- 将不同执行器、时间推进或释放协议的数值合并排序。

## 解除阻塞所需的一手材料

至少需要以下任一组可核验材料后才可重新打开 native 恢复：

1. 原始 CIE-DH 可构建源码及其 map/input；或
2. 足以唯一确定 0.2 秒执行状态、moving/stopped 计数、HOLD/BTI/DDI 和全部系数的正式算法说明，并有原作者输出用于回归。

在此之前，P0 native DH 指标统一记为 `N/A (BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED)`，而不是失败数值或零。
