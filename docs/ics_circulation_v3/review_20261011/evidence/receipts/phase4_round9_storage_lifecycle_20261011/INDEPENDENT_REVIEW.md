# 持盘机制原件独立复核

2026-10-11。独立脚本 audit_mechanisms.py 没有调用 Simulation、advance 或机制工厂。它直接读取原 JSON trace/state、合同和本地生成并绑定 SHA 的 pickle checkpoint，重建实际移动、节点/边/接收半开区间和袋盘绑定。

当前冻结源码对应的正式机制证据是 **mechanisms_004**：11 种机制 × 2 个模式的 22 个主结果，以及 44 个重放原件和 44 个完整 pickle checkpoint，独立审计全部通过：**2594 检查、0 失败、0 physics calls，CPU 0.15625 秒、wall 0.2634241 秒**。每个输入产物读取前后的 SHA 保持一致；当前目录 independent_audit_002.json 保存逐项结果及全部绑定。审计脚本 SHA 为 6fe8cb6d81b09269c20f698fb82bbe4c4539ebc69649061693a9d92449060866；冻结 storage_routing.py SHA 为 431f4e4a1baf2a20e27561ac4ef722b67223b118dda9819aa3b96fa69340b4ea。

修复前的 mechanisms_002（20 个主结果、40 个重放）和 mechanisms_003（2 个主结果、4 个重放）继续原样保留。其 independent_audit_001.json 记录 **2599 检查、0 失败、0 physics calls，CPU 0.140625 秒**。004 是 release 平台同 f 排序修复后的同一组机制复验，不能增加独立场景数。22 个 case/mode 的完成时刻、同盘存储数、复用次数、成本、终止状态和 prefix_arrive 数量与 002+003 的独立重算摘要逐字段相同；这不表示其搜索路径或逐项查询统计必然相同。

独立重算内容包括：

- 每个有限盘从初始位置沿实际 depart 事件移动，禁止关闭边、旅行重叠和路径断裂；按真实时段重建节点、边、接收容量，按半开区间处理同时释放/获取。
- 入库、出库、卸载始终由同一个已加载实体承载。库内不能卸载或产生空盘，出库不能早于真实到库和公告 release。
- 最终卸载只发生于不可变最终目的地；卸载和 hold 的时间严格按原模块，下一次空盘动作/装袋不得提前。
- 三袋完整分母、未完成袋、同盘服务顺序和复用次数直接由 trace 重建；tray_wait、empty travel ticks、backlog 与加权成本独立复算。
- 44 个重放 JSON 与各自主结果逐字段相等；44 个 checkpoint 的时钟、route mode、trace 前缀、初始有限盘集合、observed/pending 互斥且完整的身份集合及不超前的存储进度均核对。

## 发现并修复的证据缺口

mechanisms_001 仅保存20个主 raw，40次checkpoint重放只存 exact=true，没有重放 raw 或 checkpoint，不能据此独立重算。反馈后 root 保留001，新跑002，完整保存并绑定40个pickle和40个replay JSON。001与002是同场景重跑，全部CPU应计成本，但不能增加独立场景数；002 是修复前的完整原件复核，当前源码正式原件复核使用004。

原10种机制全为 protected 袋，既有 _safe_prefix 对受保护袋保留整个已验证 witness，因此标记 next_edge 的组并不构成真实分段控制证据。反馈后 root 补 unprotected_reuse 为 mechanisms_003。独立读其 next_edge trace，确认有 **2 次 prefix_arrive**，在 EBS 实际到达后重新生成后段，均保持 release；whole_route 对照没有 prefix_arrive。两组完成时刻 early1=9、early2=18、direct=24，同一盘复用2次，成本32.4。

## 负结果没有删掉

002中7种机制各2mode全部三袋完成；deadline_before_release 与 closed_ingress 的4个主结果均0/3完成；closed_return的2个主结果均1/3完成。后6个主结果继续标为 fixed_tick_cap_censored，保持未完成分母，没有把任务不可达、过紧保护、无回流掩盖为成功。这里是截止160tick的机制观察，不是完整机场工作负荷的可行性判定。

003另增加两个全部完成的主结果，来源仍是同一手工机制变体。计量物理运行数分别为002的60、003的6；本复核不新增物理运行、不把checkpoint分支算独立样本。

004 对上述全部 11 种机制重新执行 66 次物理运行，root 计量 CPU 2.96875 秒。独立复核仍保留全部 6 个 censored 主结果及其恢复分支；unprotected_reuse 的 next_edge 仍有 2 次真实 prefix_arrive。两轮独立机制审计合计 CPU **0.296875 秒**、0 次物理调用，分别归属 independent_audit_001 与 002，不与 root 的物理运行 CPU 混加为同一次调用。

一次最初写audit脚本的工具调用因 JavaScript 字符串引号语法出错而未执行、未创建文件，无物理运行；随后用同内容合法模板完成写入。该编排以及人工阅读/文档、审计摘要对照的 CPU 未计，属于 auxiliary unknown。两轮审计计量包含 pickle 反序列化及必要模块导入，不包含最终审计报告写出。
