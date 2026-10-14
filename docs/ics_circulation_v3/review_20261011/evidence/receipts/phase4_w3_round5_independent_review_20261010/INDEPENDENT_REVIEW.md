# 第五轮独立审查记录

截至 2026-10-10，本轮已授权的原件审查、全 ICS 回归和完整 nominal 机会诊断全部完成。没有 commit、push、SSH 或新外部执行。下表为各次独立检查；旧失败试验与早期检查保留。

| 检查 | 结果 | 证据 |
|---|---:|---|
| 第一版完整 ICS 回归 | 700 passed，0 failed/error/skip | `../phase4_w3_round5_validation_20261010/validation_manifest.json` |
| 最终完整 ICS 回归 | 717 passed，0 failed/error/skip；98 源文件、59 测试文件前后 SHA 相同 | `../phase4_w3_round5_final_validation_20261010/validation_manifest.json` |
| 最终回归之后的故障注入专项 | 作者另跑 2 passed；独立核对其报告、测试 SHA 和旧 157 文件不变 | `final_validation_supplement_binding.json` |
| 空盘方法 28 pilot / 252 正式 | 7,414 / 79,333 checks，均 0 errors | `empty_pilot_audit.json` / `empty_final_audit.json` |
| full-cycle 修后 pilot：初审 / 加查逐条 search 账 | 2,548 / 2,608 checks，均 0 errors | `full_cycle_pilot_audit.json` / `full_cycle_pilot_search_audit.json` |
| full-cycle 2176 请求正式原件 | 69,226 checks，0 errors；1388 unique 原件、3999 绑定文件不变 | `full_cycle_final_audit.json` |
| full-cycle 分析的独立原件对照 | 6,047 checks，0 errors；完整 17×4×32 向量及每请求任务/保护/准时/在途/成本账一致 | `full_cycle_analysis_comparison.json` |
| nominal 174 个自生成 checkpoint 绑定 | 3,037 checks，0 errors；state/cursor/private cache/slow clock/future/action key/693 请求网格一致 | `nominal_checkpoint_binding_audit.json` |
| nominal 全 693 请求与值分析 | 25,257 checks，0 errors；174 完整非空池，另 6 zero 尝试保留 | `../phase4_w3_network_nominal_analysis_20261010/audit_and_values.json` |
| nominal feature-only 覆盖 | 185 checks，0 errors；不读取 counterfactual outcome | `../phase4_w3_network_nominal_analysis_20261010/feature_coverage.json` |
| nominal 12 对机制分支逐事件账 | 74 checks，0 errors；load−arrival 与 empty departure travel_time 独立复算 | `../phase4_w3_network_nominal_analysis_20261010/mechanisms.json` |
| SAA 16 pilot / 144 正式 | 33,613 / 390,125 checks，均 0 errors；正式含 32,360 物理 proxy、36 point 物理复现 | `scenarios_pilot_audit.json` / `scenarios_final_audit.json` |

717 和随后新增 2 项属于不同运行，不能写成一次 719 项全套运行。早先 700 与最终 717 也各自确实执行过，资源账不能互相替代。

用户原 C++ `cpp/ics_core/runtime/bounded_local_pibt.hpp` SHA 保持 `b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951`。700→717 之间原源集中仅 `empty_improvement.py` 加入两个扩展 hook，新增 factorial/scenarios 四个源文件及两个测试文件；原默认配置通过全部 36 个 factorial 实体轨迹复现。717 之后仅增加上述一个故障注入测试文件，其余源和测试未变。

停止判据已检查整任务 ledger，而非只检查已观察的任务；包括尚未到达、载袋/卸载、既有在途、计划、空盘目标、接收/边/有限占位、未来已声明预测的 TTL 和实际慢层时钟。唯一允许的长期 reservation 是与已经空闲的同一实体盘当前 node 严格一致的 INFINITY 库存占位。错误 node、未来 start、有限 end、edge/reception 均不能据此豁免。完整周期必须记录至少 h80，再经过预测有效期和一个实际 slow 周期；最终 stop tick 不应冒充首次 task_complete 或 transport_drained 时刻。

full-cycle 原件独立核实了启动时旧 root manifest 的 SHA、整个旧输入链、源/测试冻结，以及旧 h80 的所有非 `_ms` 物理字段、每一条 query 和 work、cache_before。原件没有单存 cache_after80，因此没有声称对该项做过独立逐字段比较。完整 2176 请求均 quiet；请求加权的 16572 任务实例全部完成且准时，h80 只有 14372 已观察、12436 已完成。这些是相关的请求实例，不是 16572 个独立运营任务。

固定旧 17 非空状态的 32-future 结果仍为 16 个全成本向量平坦、9 个 continuation 全平坦，17 个 optset 与 h80 一致，旧 choice 和 baseline 的完整周期 regret 都为零。它只能说明旧采样域。全 actual nominal 机会则有 180 次尝试、174 非空，实际正常池是 172×4 + 1×2 + 1×3 = 693；最初把 K4 上界 696 当成精确分母的 preflight 失败保留，修复目录逐字节复用三次已完成 collection，没有补造候选或缩减实际分母。

完整 nominal 诊断发现 25/174 个完整周期非平坦池，实际 Timed 选择在 12 个池非最优，全部在 counterflow，其中 11 个 continuation、1 个 origin；最大单状态局部 regret 为 45.7。旧 18 个样本只覆盖 17 个非空池，且没有覆盖这 12 个机会。另有 51 个成本平坦池具有不同完成时间向量或终态盘位置，不能等同为物理轨迹相同。全部状态、25/12/51 分类以及完整 12 表分别在 `audit_and_values.json`、`mechanisms.json`、`NOMINAL_ALL12_TABLE.md`。

最强 d40 的替代当前路径使当前袋完成晚 18 tick 但仍准时，通过改变随后空盘释放/承诺，避免昂贵的先行跨 zone 调盘，使下一袋早 40 tick 完成；全期 queue wait −40、empty distance −57，J −45.7。普通 d19 也保留了当前袋变慢及其他后续袋变慢的代价。`NOMINAL_MECHANISMS.md` 给出真实事件链。此作用依赖原固定 slow/reactive continuation 和成本权重，并非证明当前袋更快、某条边发生容量瓶颈或一般 ML 路由优势。26 与 46 同 logistics zone 但不同 control_partition，也不能无条件套用 W2 same-owner guard。

全 nominal 只复用了一个实际未来；这些是沿同一路径相关状态的单步偏离值。局部 regret 的和不是可实现 episode 节省，不是 32-future 均值，也不是独立确认或挑选下一训练集的依据。旧 32-future 与新全机会 nominal 两套证据并列保留。

SAA 独审覆盖发布时点、已观察单位去重、public proxy、共同情景请求、重复场景的权重、物理 memo、均值、每情景预算、选择/tie/fallback、完整任务和静默排空，以及 point 与 factorial 对应配置的 36 次原件复现。其 8 场景使每动作的物理计算预算增加，合成先验未校准，不能据此称同 CPU 预算优势或实际运营鲁棒性。

每次审查的 CPU/wall 保存在相应 JSON。完整第五轮资源、失败下界和未知部分见 `../phase4_w3_round5_resource_ledger_20261010/final/RESOURCE_LEDGER.md`，不把嵌套 branch/collection 计量重复相加。审计脚本的原位置为 `.tmp/`；本目录与 nominal analysis 目录中的副本用于保存实际运行源码及 SHA，包含相对根路径假设，重跑应恢复原目录结构。没有未完成的物理实验或审查事项。
