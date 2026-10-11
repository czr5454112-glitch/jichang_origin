# Round9 业务输入独立复核

2026-10-11。复核者未实现 `business_inputs.py`，本次未修改该模块或其 author tests。审查源 SHA-256：`e1a9b4fbde6c7d2a737e2c2fafefe9145c042a44ee408b6935dfe3799a5fa13b`。

**本轮未发现需阻断输入层的确定错误。** 这只覆盖纯输入边界和已发布的 audit_003 输入产物；新 business runtime adapter、运行仿真、现场参数有效性须另行验证。没有把文件一致性解释成现场真实性认证。

## 独立反例

新增 `tests/test_ics_v3_business_input_audit.py`，不导入实现者测试或其 fixture。14 项全部通过。自建三袋 fixture 使用不连续 ID、非 ID 顺序、与投射不同的原 timetable OD，以及紧靠 4800 秒阈值的高精度小数：

- 生命周期在源秒级判断，不能先把到达取整再把 direct 变成 early；源 ID 42/7 的手算类别不同且保留。
- arrival 向上、final hard deadline 向下；极小 lead 与 Decimal 全局 precision=2 仍不能放宽 deadline。
- 存在 `arrival > deadline` 的袋以及完全无边的图时保留全部业务袋，既不删分母，也不把 canonical segment ID 当真实托盘。
- 任一袋被漏掉、source bytes 变化、同一原航班组被拆到不同最终目的地均拒绝；即使同步重绑所有新产物 SHA，语义反例仍能触发。
- normalized 行重排不改变输出业务身份或字段；全量环境 tape 明示私有，输入层不调用或构造 Simulation / Tray / StorageBag。

## 全文件复算

独立脚本不调用 `load_business_workload` 产生期望值：直接逐行读取原 raw 文本，以标准库 Fraction 重算所有 arrival/deadline/release/publication，核对已发布的 clock-binding 文件。另重建正容量有向图闭包、原始父 ID 集和派生 parent rank、整航班时间平移一致性。

| 规模 | 完整袋数 | early / direct | 去程静态不连通且保留 | storage 链不连通且保留 |
|---|---:|---:|---:|---:|
| 1× | 28506 | 15097 / 13409 | 4001 | 4001 |
| 2× | 57012 | 30194 / 26818 | 8002 | 8002 |

全部原始父任务在每个规模恰好一次；2× 每个派生父任务恰好一次，时间平移保持每袋相对父 STD 差及整航班组一致。父表仍是一个 timetable 源，独立观测运营日数为 0。所有输入路径 SHA、clock-binding SHA 与代码前后 SHA 均一致。

run_001 完成 940734 次逐字段/逐身份检查、14 tests，CPU 4.6875 秒。补充完整 parent 身份链后 run_002 完成 1311318 次检查、14 tests，CPU 6.265625 秒；二者全部通过，无失败重跑。总已计量 CPU **10.953125 秒**。这些检查数量是机械工作量计数，不是证据强度或独立样本数。测试与全量复核共处同一 CPU 区间，不重复累加子项；纯输入复核 physical calls = 0。

## 解释边界

SHA 绑定证明使用的文件字节相同，不能单独证明原文件来自真实现场。当前独立复核支持“既有 Round8 规范化源及旧投射的一致导入”，没有重写 Round8 的来源真实性判断，也没有将派生增密当新观测日。

纯输入 schema 明示 `runtime_adaptation_required=True`；库位/等待许可、11 初盘、all-protected、STD-minus-0、1 秒 tick 是 author audit 的显式代理示例，不是现场合同或自动建议的正式参数。未来完整运行必须共同使用显式 runtime 合同，按观测时刻逐袋揭示，不能把整个 BusinessWorkload.tasks 交给在线控制器。

源阅读、审查判断、文档和工具编排 CPU 没有统一计量，记 unknown auxiliary。结果写入前的测量区间未包括 Python startup、源快照与最终 evidence write。

## 运行适配器审查发现与修复后复核

随后独立静态审 business_runtime.py 时发现了确定的合同绕过：只凭 BusinessWorkload 的类型和 input contract ID 接受任务对象，dataclasses.replace 可移除保护、同时放宽 deadline_seconds/deadline，或把 early 改 direct 后清空storage字段；旧总分母与时钟一致性检查仍可能通过。这一问题已反馈实现者并得到确认。本审查没有在修复前执行独立probe，故不把静态发现写成一次失败实测。

实现者修复为完整 BusinessWorkload 内容SHA封印，adapter检查封印，并逐任务重算原合同要求的 final deadline、protected、early阈值及scheduled release。封印明示用于防误改，不冒称能认证恶意调用者重新签署的来源；逐字段策略复核对常见主动重封篡改再拒绝。

修复后独立 probe_adapter_repair.py 使用本复核自己的fixture，分别对移除保护、放宽最终截止、删除早包存储、提前release进行未重封/主动重封两组8反例，全部拒绝。未重封由content binding捕获，重封仍分别由保护/截止/lifecycle/release政策捕获。还独立核对干净适配保持3袋/1盘、初始公开bags/progress为空、精确正小数旅行向上取整和关闭边不变。该probe不运行physics，CPU **0.375秒**。

修复源冻结后 run_003 对最新 author audit_004 再跑14独立tests及85518条完整逐字段/父子身份核验，1311318检查全部通过，CPU **6.15625秒**。新输入源SHA为 be26793baf4ad61dfcd6122b2af2b67898f384e4f9d25771bbff23d1ca97eddf；适配源SHA为 9fd5820d4a5b48e9f8f1e56469945b83b6c8680747b1cc8999f3a5c76b67d305。

本目录累计已计量独立输入复核与适配probe CPU现在为 **17.484375秒**（4.6875 + 6.265625 + 6.15625 + 0.375），此前全部记录保留。三次完整核验只是不同审查阶段的计算工作，不能声称增加独立业务样本。
