# 第七轮标签阶段交接

从原始三个 nominal 初态安装冻结的 same_zone32plus32 控制器，现场重新采到 **180 次尝试：174 个非空状态、6 次零候选、692 个候选**。所有检查点立即复制真实 cursor、私有 replay cache、待到达账本和实际继续策略合同，没有用可见状态重建 checkpoint。

三个 collection 对第六轮 formal nominal 的完整结果（仅排除 policy_stats 中计时 *_ms）、逐次 search、cache、机会、selector/event/兼容 physical trace 和 slow clock 全部精确一致。5 个正常恢复分支在共同绝对终点再次严格复现；16 个固定 pilot、历史 12 状态 × 4 候选、正式全部 692 候选均完成真实任务账和 controller-quiescent，失败/截断为 0，memo 为 0。

历史 12 状态明确属于旧策略轨迹的事后诊断子组，只更换未来慢控制器；state/cursor/cache/pool/clock 保持原值。d40 c0/c1 的 148.1/146.7、h80、全结果、逐查询、cache 与停止时刻逐字段复现第六轮。

| 阶段 | 实际物理调用 | Worker invocation CPU 秒 | Parent run CPU 秒 | 阶段墙钟秒 |
|---|---:|---:|---:|---:|
| collection_run | 3 | 147.296875 | 0.437500 | 74.722241 |
| normal_resume | 5 | 148.421875 | 1.046875 | 43.507384 |
| pilot | 16 | 283.718750 | 1.093750 | 51.931294 |
| old12 | 48 | 1198.578125 | 0.437500 | 214.682295 |
| full | 692 | 10051.593750 | 2.109375 | 1702.097760 |

另有 prepare 5.781250 CPU 秒、12 checkpoint 转换 5.609375 CPU 秒（0 次物理仿真）。上述已知标签流水线 CPU 下界为 **11846.125000 秒**，记录了 **764 次物理调用**。完整边界、逐阶段资源与路径见 `label_resource_summary.json`。

CPU 是函数计时范围，不是操作系统全生命周期总量：worker/CLI import、启动及少量计时后的 receipt/manifest 写入未单独测量。raw 中 cycle CPU 已包含在 worker invocation，search/work 也只是嵌套工作账，禁止重复加总。单 worker lifetime 内存峰值不能当多进程同时总峰。

冻结前作者两次 7 项测试各有 2 项 normal-resume 审计断言失败：先混用了完整 trace 与 suffix 索引，再遗漏 result() 的非执行 terminal tick preview；物理结果/搜索/cache 一直相同。修复后作者 7 项通过，随后独立 29 项通过；失败、诊断工具墙钟及未知 child CPU 明确保存在作者记录。正式 5 个 normal 分支没有失败。故障注入测试覆盖 partial query pickle、raw/recovery 写失败与已完成物理结果保留；其测试资源由独立审查记录计费。

独立纯文件复算（0 新仿真）：

- 全部 174 状态 / 692 raw 候选逐账核对；非平坦状态 20，实际选择非最优状态 0，最大局部 regret 0。
- 全部相同 bag 完成时刻均不晚于实际选择的候选子集（允许完全相等），最小 J 仍可改善的状态 0，最大可改善 0。
- 再要求 load_time 也不晚的更严子集，可改善状态 0，最大可改善 0；相同缺失初始 load_time 只视为未变，不猜测具体时间。
- 核验 CPU 150.500000 秒，墙钟 152.222182 秒；原 full manifest 前后字节不变。逐状态 cost vector、optset 和子集在 `independent_choice_check/result.json`。

另做 J 不高于实际选择、所有 bag 完成不晚且至少一件严格更早的服务诊断：**0 个状态 / 0 个候选**满足；再要求 load_time 也不晚后为 **0 个状态 / 0 个候选**。完整 174 状态含空集合逐池列出，见 `independent_choice_check/service_ties_result.json`。该额外纯文件核验 CPU 30.890625 秒、墙钟 31.303293 秒，未新增物理实验。

这些是离线同一 nominal tape、单次动作偏离诊断，不是在线服务保证，也不是 174 个独立部署试验；局部 regret 不可相加称为可部署节省。692 候选任务账的重复计数不是新的独立真实任务源。仍只有三个重复使用的合成开发流，没有扩展为独立运行日或新的实物流量源。

停止合同没有降低：全部固定任务已观察且完成、pending arrivals 为空、实际运输承诺排空、所有原预测公示与 TTL 过期，并经历完整真实 slow period 和实际 trigger。有限资源/tick cap 会显式记 censored，不会冒称不可行。未来任务仅供物理引擎和离线评价，控制器仍只读原公开预测和已观察状态。

兼容 physical trace 沿用了冻结旧 helper；completed/load_times/empty_targets 字典可能反映后续更新，不能把这三项当即时 tick 账本。准确服务时点来自完整任务 ledger、event trace、真实 checkpoint 和 milestone；root 另补 immutable 即时 trace 复跑。本批控制、成本和搜索未使用这些输出 trace。checkpoint fingerprint 沿用旧 _semantic 的 *_ms 排除规则，实际控制标量（含 planning_budget_ms）另有 active continuation 显式绑定。

全部新代码与测试快照在 `source_snapshot/`、`test_snapshot/`：104 source、67 tests，所有正式阶段结束均报告 source/input/test 不变。原 C++ `cpp/ics_core/runtime/bounded_local_pibt.hpp` 直接纳入输入 SHA，未修改。没有 commit/push。

证据入口：`protocol.json`、`preparation_manifest.json`、`collection_run/summary.json`、`normal_resume/summary.json`、`pilot/summary.json`、`old12/summary.json`、`full/summary.json` 及各自 manifest。独立 reviewer 的终审与 root 主分析另行引用，不能把本纯文件交叉核验替代完整审计。
